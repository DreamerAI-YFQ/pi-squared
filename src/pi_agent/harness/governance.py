"""治理（对应 ETCLOVG 的 G 层，特色实现）。

权限模型（allowlist/denylist）+ 审计日志（JSONL）。
通过 before_tool_call / after_tool_call 钩子接入 agent 循环。
"""
import json
import time


class Governance:
    """治理策略：工具权限检查 + 审计日志。"""

    def __init__(
        self,
        allowlist: list[str] | None = None,
        denylist: list[str] | None = None,
        audit_path: str | None = None,
    ):
        # allowlist 为 None 表示"不限制"（全部允许）；否则只允许列表内的工具
        self._allowlist: set[str] | None = set(allowlist) if allowlist is not None else None
        self._denylist: set[str] = set(denylist) if denylist else set()
        self._audit_path = audit_path

    async def before_tool_call(self, tool_call, args) -> dict | None:
        """执行前钩子：权限检查。返回 {"block": True, "reason": ...} 则阻断。"""
        name = tool_call.name
        if self._allowlist is not None and name not in self._allowlist:
            return {"block": True, "reason": f"工具 {name} 不在允许列表"}
        if name in self._denylist:
            return {"block": True, "reason": f"工具 {name} 被禁止"}
        return None

    async def after_tool_call(self, tool_call, result, is_error) -> dict | None:
        """执行后钩子：审计记录。"""
        self._audit(tool_call, is_error)
        return None

    def _audit(self, tool_call, is_error: bool) -> None:
        if not self._audit_path:
            return
        record = {
            "tool": tool_call.name,
            "args": tool_call.arguments,
            "isError": is_error,
            "timestamp": int(time.time() * 1000),
        }
        with open(self._audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
