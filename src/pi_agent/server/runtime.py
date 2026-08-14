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
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from pi_agent.harness.env import LocalExecutionEnv
from pi_agent.harness.harness import AgentHarness
from pi_agent.harness.session.context import build_session_context
from pi_agent.harness.session.session import Session
from pi_agent.harness.session.storage import JsonlSessionStorage
from pi_agent.harness.tools.bash import create_bash_tool
from pi_agent.harness.tools.edit import create_edit_tool
from pi_agent.harness.tools.read import create_read_tool
from pi_agent.harness.tools.write import create_write_tool
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
    """单个会话的运行时：harness + 事件队列。"""

    def __init__(self, session_id: str, data_dir: Path, workspace: Path, stream_fn: StreamFn):
        self.id = session_id
        self.data_dir = data_dir
        self.workspace = workspace
        self.session_path = data_dir / "sessions" / session_id / "session.jsonl"
        self._queue: asyncio.Queue | None = None
        self._busy = False

        env = LocalExecutionEnv(cwd=str(workspace))
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        session = Session(JsonlSessionStorage.create(str(self.session_path), session_id=session_id))
        tools = [create_read_tool(), create_write_tool(), create_edit_tool(), create_bash_tool()]

        self._harness = AgentHarness(
            stream_fn=stream_fn,
            env=env,
            session=session,
            harness_tools=tools,
            system_prompt=SYSTEM_PROMPT,
            event_listeners=[self._on_event],
        )
        self._session = session

    @property
    def busy(self) -> bool:
        return self._busy

    async def _on_event(self, event) -> None:
        """Agent 事件 listener：推入当前活跃的 SSE 队列。"""
        if self._queue is not None:
            await self._queue.put(event)

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


def resolve_stream_fn() -> tuple[StreamFn, str]:
    """根据环境选择 provider：有 key 用 DeepSeek，否则 faux（开箱即用）。"""
    from pi_agent.providers.openai import _load_dotenv, deepseek_stream

    _load_dotenv()
    if os.environ.get("DEEPSEEK_API_KEY"):
        return deepseek_stream, "deepseek"
    from pi_agent.providers.faux import faux_stream

    return faux_stream, "faux"


class Registry:
    """所有会话运行时的注册表 + 磁盘目录扫描。"""

    def __init__(self, data_dir: Path, workspace_root: Path):
        self.data_dir = data_dir
        self.workspace_root = workspace_root
        self._runtimes: dict[str, SessionRuntime] = {}
        self._stream_fn, self.provider_mode = resolve_stream_fn()

    def create_session(self) -> SessionRuntime:
        session_id = str(uuid.uuid4())[:8]
        workspace = self.workspace_root / session_id
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = SessionRuntime(session_id, self.data_dir, workspace, self._stream_fn)
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
        runtime = SessionRuntime(session_id, self.data_dir, workspace, self._stream_fn)
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
