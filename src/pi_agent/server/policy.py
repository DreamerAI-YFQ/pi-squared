"""M2 治理：路径 allowlist + 人工审批 + 审计。

三层防线（先原理）：
1. 路径守卫（硬边界）：文件工具的 path 必须落在 workspace 内，越界直接 block。
   这是机器强制执行的，不依赖人。
2. 人工审批（交互边界）：写操作（write/edit/bash 等）执行前挂起，
   通过 SSE 发 approval_request 给前端，用户批准才继续。
   bash 无法做路径级静态分析（cd/子进程可逃逸），由审批兜底。
3. 审计（事后追溯）：所有 blocked / 请求 / 结果 落 JSONL，
   格式对齐 harness/governance.py 并加 kind 字段。

接入点：agent_loop 的 before_tool_call / after_tool_call 钩子
（AgentHarness 已透传），核心循环零改动。
"""
import asyncio
import json
import time
import uuid
from pathlib import Path

APPROVAL_TIMEOUT_S = 300  # 审批等待上限：超时视为拒绝


def _now_ms() -> int:
    return int(time.time() * 1000)


class PolicyConfig:
    """治理配置（data_dir/config.json）。

    autoApprove：免审批工具列表（默认只读工具 read 直接放行，
    写类工具 write/edit/bash 一律审批）。
    """

    def __init__(self, data_dir: Path):
        self.path = data_dir / "config.json"
        self.auto_approve: set[str] = {"read"}

    def load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.auto_approve = set(data.get("autoApprove", ["read"]))
            except (json.JSONDecodeError, OSError):
                pass

    def save(self) -> None:
        self.path.write_text(
            json.dumps({"autoApprove": sorted(self.auto_approve)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class PathGuard:
    """路径守卫：workspace 硬边界。"""

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()

    def check(self, path_str: str) -> str | None:
        """检查路径是否在 workspace 内。合法返回 None，越界返回原因。"""
        target = (self.workspace / path_str).resolve()
        if target != self.workspace and self.workspace not in target.parents:
            return (
                f"路径越界：{path_str} 解析为 {target}，"
                f"不在工作区 {self.workspace} 内。请只操作工作区内的路径。"
            )
        return None


class ApprovalManager:
    """审批管理器：挂起工具执行，等前端批准。

    协议（server 层事件，直接进 SSE 流）：
        -> {"type": "approval_request",  "approvalId", "toolName", "args"}
        <- POST /api/sessions/{sid}/approvals/{aid} {"approved": bool}
        -> {"type": "approval_resolved", "approvalId", "approved", "reason"}
    """

    def __init__(self, emit, audit):
        self._emit = emit  # async fn(dict)：往 SSE 队列塞事件
        self._audit = audit  # fn(kind, **record)：写审计
        self._pending: dict[str, asyncio.Future] = {}

    @property
    def has_pending(self) -> bool:
        return len(self._pending) > 0

    async def request(self, tool_name: str, args: dict) -> tuple[bool, str]:
        """发起审批请求并挂起，返回 (是否批准, 原因)。"""
        approval_id = str(uuid.uuid4())[:8]
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[approval_id] = future
        self._audit("approval_request", tool=tool_name, args=args, approvalId=approval_id)
        await self._emit(
            {"type": "approval_request", "approvalId": approval_id, "toolName": tool_name, "args": args}
        )
        try:
            approved = await asyncio.wait_for(future, timeout=APPROVAL_TIMEOUT_S)
            reason = "用户批准" if approved else "用户拒绝"
        except asyncio.TimeoutError:
            approved, reason = False, f"审批超时（{APPROVAL_TIMEOUT_S}s），默认拒绝"
        finally:
            self._pending.pop(approval_id, None)
        self._audit("approval_result", tool=tool_name, approvalId=approval_id, approved=approved, reason=reason)
        await self._emit(
            {
                "type": "approval_resolved",
                "approvalId": approval_id,
                "approved": approved,
                "reason": reason,
            }
        )
        return approved, reason

    def resolve(self, approval_id: str, approved: bool) -> bool:
        """前端响应审批。返回是否成功（不存在的 id 返回 False）。"""
        future = self._pending.get(approval_id)
        if future is None or future.done():
            return False
        future.set_result(approved)
        return True


def make_hooks(workspace: Path, approvals: ApprovalManager, auto_approve: set[str]):
    """构造 before/after 钩子（agent_loop 认识的签名）。

    before：路径守卫 → 免审批放行 → 审批挂起。
    after：审计记录。
    """

    guard = PathGuard(workspace)

    async def before_tool_call(tool_call, args):
        name = tool_call.name

        # 1. 路径守卫：文件类工具先检查边界（read 免审批也必须过这关）
        if name in ("read", "write", "edit") and "path" in args:
            violation = guard.check(args["path"])
            if violation:
                approvals._audit("blocked", tool=name, args=args, reason=violation)
                return {"block": True, "reason": violation}

        # 2. 免审批工具直接放行
        if name in auto_approve:
            return None

        # 3. 其余工具（写操作/bash）走人工审批
        approved, reason = await approvals.request(name, args)
        if not approved:
            return {"block": True, "reason": f"操作未获批准：{reason}"}
        return None

    async def after_tool_call(tool_call, result, is_error):
        approvals._audit("tool_result", tool=tool_call.name, args=tool_call.arguments, isError=is_error)
        return None

    return before_tool_call, after_tool_call
