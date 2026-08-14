from pydantic import BaseModel

from pi_agent.harness.result import get_or_throw
from pi_agent.harness.tools.types import HarnessTool, ToolContext
from pi_agent.types import AgentToolResult, TextContent


class BashParams(BaseModel):
    command: str
    timeout: float | None = None


def create_bash_tool() -> HarnessTool:
    """创建 bash 工具（对应 pi 的 bash.ts 的简化版）。"""

    async def bash(tool_call_id: str, params: dict, context: ToolContext) -> AgentToolResult:
        env = context.env
        command = params["command"]
        timeout = params.get("timeout")

        result = get_or_throw(env.exec(command, timeout=timeout))

        text = result.stdout
        if result.stderr:
            text += f"\n[stderr]\n{result.stderr}"
        if result.exit_code != 0:
            text += f"\n[exit code: {result.exit_code}]"

        return AgentToolResult(content=[TextContent(text=text)], details={})

    return HarnessTool(
        name="bash",
        description="执行 shell 命令，返回 stdout/stderr 和退出码。",
        parameters=BashParams,
        execute=bash,
    )
