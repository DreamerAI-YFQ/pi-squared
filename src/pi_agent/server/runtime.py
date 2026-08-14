"""会话运行时注册表：session_id → 运行中的 AgentHarness + 事件队列。

设计：
- 每个会话一个 SessionRuntime，持有 harness、workspace 路径、事件队列。
- prompt 期间事件队列激活，Agent 事件 listener 把事件推入队列，
  SSE 端点消费队列直到收到哨兵（None）。
- 同一会话同一时刻只允许一个 prompt（busy 检查）。
"""
import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from pi_agent.extensions.observability import Observability
from pi_agent.harness.env import LocalExecutionEnv
from pi_agent.harness.harness import AgentHarness
from pi_agent.harness.session.context import build_session_context
from pi_agent.harness.session.session import Session
from pi_agent.harness.session.storage import JsonlSessionStorage
from pi_agent.harness.tools.bash import create_bash_tool
from pi_agent.harness.tools.edit import create_edit_tool
from pi_agent.harness.tools.read import create_read_tool
from pi_agent.harness.tools.write import create_write_tool
from pi_agent.server.policy import ApprovalManager, PolicyConfig, make_hooks
from pi_agent.stream_fn import StreamFn

SYSTEM_PROMPT = (
    "你是一个 coding 智能体，在本地文件系统的工作区内工作。"
    "使用提供的工具（read/write/edit/bash）完成任务，先想清楚步骤再调用工具，"
    "操作完成后用简短的中文总结结果。"
)


@dataclass
class SessionInfo:
    """会话元信息（列表页用）。"""

    id: str
    title: str
    created_at: int
    updated_at: int
    workspace: str


class SessionRuntime:
    """单个会话的运行时：harness + 事件队列 + 治理（审批/审计）。"""

    def __init__(
        self,
        session_id: str,
        data_dir: Path,
        workspace: Path,
        stream_fn: StreamFn,
        auto_approve: set[str] | None = None,
        model_name: str = "faux",
    ):
        self.id = session_id
        self.data_dir = data_dir
        self.workspace = workspace
        self.session_path = data_dir / "sessions" / session_id / "session.jsonl"
        self.audit_path = data_dir / "sessions" / session_id / "audit.jsonl"
        self.trace_path = data_dir / "sessions" / session_id / "trace.json"
        self.model_name = model_name
        self._queue: asyncio.Queue | None = None
        self._busy = False
        # 可观测性（M3）：span 树 + token/成本，由事件流驱动
        self.obs = Observability()

        env = LocalExecutionEnv(cwd=str(workspace))
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        session = Session(JsonlSessionStorage.create(str(self.session_path), session_id=session_id))
        tools = [create_read_tool(), create_write_tool(), create_edit_tool(), create_bash_tool()]

        # 治理（M2）：路径守卫 + 审批 + 审计，通过 agent_loop 钩子接入
        self.auto_approve: set[str] = set(auto_approve) if auto_approve is not None else {"read"}
        self.approvals = ApprovalManager(emit=self._emit_event, audit=self._write_audit)
        before_tool_call, after_tool_call = make_hooks(
            workspace=workspace, approvals=self.approvals, auto_approve=self.auto_approve
        )

        self._harness = AgentHarness(
            stream_fn=stream_fn,
            env=env,
            session=session,
            harness_tools=tools,
            system_prompt=SYSTEM_PROMPT,
            before_tool_call=before_tool_call,
            after_tool_call=after_tool_call,
            event_listeners=[self._on_event],
        )
        self._session = session

    @property
    def busy(self) -> bool:
        return self._busy

    async def _on_event(self, event) -> None:
        """Agent 事件 listener：观测追踪 + 推入当前活跃的 SSE 队列。"""
        self._obs_track(event)
        if self._queue is not None:
            await self._queue.put(event)

    def _obs_track(self, event) -> None:
        """把 Agent 事件流翻译成 span 树 + 指标（O 层）。

        层级：agent_prompt → turn → tool:{name}
        LLM usage 挂到 turn span 的 attrs 上（一个 turn 恰好一次 LLM 调用）。
        """
        kind = getattr(event, "type", None)
        if kind == "agent_start":
            self.obs.start_span("agent_prompt")
        elif kind == "turn_start":
            self.obs.start_span("turn")
        elif kind == "message_end":
            msg = getattr(event, "message", None)
            if getattr(msg, "role", None) == "assistant" and getattr(msg, "usage", None):
                usage = msg.usage
                self.obs.record_usage(self.model_name, usage.prompt_tokens, usage.completion_tokens)
                self.obs.annotate(tokens=usage.total_tokens)
        elif kind == "tool_execution_start":
            self.obs.start_span(
                f"tool:{event.toolName}", tool=event.toolName, args=str(event.args)[:200]
            )
        elif kind == "tool_execution_end":
            self.obs.record_tool(event.toolName, event.isError)
            self.obs.annotate(isError=event.isError)
            self.obs.end_span()  # tool span
        elif kind == "turn_end":
            self.obs.end_span()  # turn span
        elif kind == "agent_end":
            self.obs.end_span()  # root span
            self.obs.save(str(self.trace_path))

    def observability_snapshot(self) -> dict:
        """观测快照：内存态优先，runtime 重挂载后回退读 trace.json。"""
        if self.obs.events or self.obs.spans:
            return {
                "model": self.model_name,
                "spans": self.obs.spans,
                "events": self.obs.events,
                "totalTokens": self.obs.total_tokens,
                "totalCost": round(self.obs.total_cost, 6),
                "llmCalls": len(self.obs.llm_calls()),
                "toolCalls": len(self.obs.tool_calls()),
            }
        if self.trace_path.exists():
            try:
                data = json.loads(self.trace_path.read_text(encoding="utf-8"))
                data.setdefault("model", self.model_name)
                return {
                    "model": data.get("model", self.model_name),
                    "spans": data.get("spans", []),
                    "events": data.get("events", []),
                    "totalTokens": data.get("total_tokens", 0),
                    "totalCost": round(data.get("total_cost", 0.0), 6),
                    "llmCalls": sum(1 for e in data.get("events", []) if e.get("kind") == "llm_call"),
                    "toolCalls": sum(1 for e in data.get("events", []) if e.get("kind") == "tool_call"),
                }
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "model": self.model_name,
            "spans": [],
            "events": [],
            "totalTokens": 0,
            "totalCost": 0.0,
            "llmCalls": 0,
            "toolCalls": 0,
        }

    async def _emit_event(self, event: dict) -> None:
        """server 层事件（审批等）：同样进 SSE 队列。"""
        if self._queue is not None:
            await self._queue.put(event)

    def _write_audit(self, kind: str, **record) -> None:
        """审计落盘：blocked / approval_request / approval_result / tool_result。"""
        entry = {"kind": kind, "timestamp": int(time.time() * 1000), **record}
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    async def load_messages(self) -> list[dict]:
        """从 JSONL 重放会话历史（恢复用）。"""
        entries = sorted(await self._session.find_entries(), key=lambda e: e.seq)
        messages = build_session_context(entries)
        from pi_agent.server.serialize import to_jsonable

        return [to_jsonable(m) for m in messages]

    async def stream_events(self, text: str):
        """跑一次 prompt，把事件流以 SSE 帧的格式逐条 yield。"""
        if self._busy:
            raise RuntimeError("会话正忙")
        self._busy = True
        queue: asyncio.Queue = asyncio.Queue()
        self._queue = queue

        async def _run() -> None:
            try:
                await self._harness.prompt(text)
            except asyncio.CancelledError:
                await queue.put({"type": "server_error", "message": "运行被取消"})
            except Exception as exc:  # noqa: BLE001 — 任何运行异常都转成事件发给前端
                await queue.put({"type": "server_error", "message": f"{type(exc).__name__}: {exc}"})
            finally:
                await queue.put(None)  # 哨兵：流结束

        task = asyncio.create_task(_run())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                from pi_agent.server.serialize import serialize_event

                payload = json.dumps(serialize_event(event), ensure_ascii=False)
                yield f"data: {payload}\n\n"
            await task
        finally:
            self._queue = None
            self._busy = False


def resolve_stream_fn(provider: str = "auto") -> tuple[StreamFn, str]:
    """选择 provider：faux / deepseek / auto（auto=有 key 用 deepseek，否则 faux）。"""
    from pi_agent.providers.faux import faux_stream

    if provider == "faux":
        return faux_stream, "faux"
    from pi_agent.providers.openai import _load_dotenv, deepseek_stream

    if provider == "deepseek":
        return deepseek_stream, "deepseek"
    _load_dotenv()
    if os.environ.get("DEEPSEEK_API_KEY"):
        return deepseek_stream, "deepseek"
    return faux_stream, "faux"


class Registry:
    """所有会话运行时的注册表 + 磁盘目录扫描 + 治理配置。"""

    def __init__(
        self,
        data_dir: Path,
        workspace_root: Path,
        policy_config: PolicyConfig | None = None,
        provider: str = "auto",
    ):
        self.data_dir = data_dir
        self.workspace_root = workspace_root
        self._runtimes: dict[str, SessionRuntime] = {}
        self._stream_fn, self.provider_mode = resolve_stream_fn(provider)
        # 观测/成本计算用的模型名（与 PRICING 表对齐）
        self.model_name = "deepseek-chat" if self.provider_mode == "deepseek" else "faux"
        self.policy_config = policy_config or PolicyConfig(data_dir)
        self.policy_config.load()

    def create_session(self) -> SessionRuntime:
        session_id = str(uuid.uuid4())[:8]
        workspace = self.workspace_root / session_id
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = SessionRuntime(
            session_id, self.data_dir, workspace, self._stream_fn,
            auto_approve=set(self.policy_config.auto_approve),
            model_name=self.model_name,
        )
        self._runtimes[session_id] = runtime
        return runtime

    def get(self, session_id: str) -> SessionRuntime | None:
        return self._runtimes.get(session_id)

    def open_session(self, session_id: str) -> SessionRuntime | None:
        """打开（或重新挂载）磁盘上已有的会话。"""
        if session_id in self._runtimes:
            return self._runtimes[session_id]
        path = self.data_dir / "sessions" / session_id / "session.jsonl"
        if not path.exists():
            return None
        workspace = self.workspace_root / session_id
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = SessionRuntime(
            session_id, self.data_dir, workspace, self._stream_fn,
            auto_approve=set(self.policy_config.auto_approve),
            model_name=self.model_name,
        )
        self._runtimes[session_id] = runtime
        return runtime

    def list_sessions(self) -> list[SessionInfo]:
        """扫描磁盘上的会话目录，返回元信息列表（按更新时间倒序）。"""
        sessions_dir = self.data_dir / "sessions"
        result: list[SessionInfo] = []
        if sessions_dir.exists():
            for session_dir in sessions_dir.iterdir():
                jsonl = session_dir / "session.jsonl"
                if not jsonl.exists():
                    continue
                info = self._scan_session(session_dir.name, jsonl)
                if info:
                    result.append(info)
        result.sort(key=lambda s: s.updated_at, reverse=True)
        return result

    def _scan_session(self, session_id: str, jsonl: Path) -> SessionInfo | None:
        """读 JSONL 提取标题（第一条用户消息）和时间戳。"""
        title = "新会话"
        created_at = 0
        with open(jsonl, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("kind") == "header":
                    created_at = d.get("createdAt", 0)
                elif d.get("kind") == "entry" and d.get("type") == "message" and title == "新会话":
                    msg = d.get("message") or {}
                    if msg.get("role") == "user":
                        content = msg.get("content")
                        if isinstance(content, str):
                            title = content[:50] or title
                        elif isinstance(content, list):
                            texts = [c.get("text", "") for c in content if isinstance(c, dict)]
                            title = ("".join(texts))[:50] or title
        stat = jsonl.stat()
        workspace = self.workspace_root / session_id
        return SessionInfo(
            id=session_id,
            title=title,
            created_at=created_at,
            updated_at=int(stat.st_mtime * 1000),
            workspace=str(workspace),
        )
