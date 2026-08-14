from pydantic import BaseModel

from pi_agent.harness.result import get_or_throw
from pi_agent.harness.tools.types import HarnessTool, ToolContext
from pi_agent.types import AgentToolResult, TextContent


class WriteParams(BaseModel):
    path: str
    content: str


def create_write_tool() -> HarnessTool:
    """创建 write 工具（对应 pi 的 write.ts）。"""

    async def write(tool_call_id: str, params: dict, context: ToolContext) -> AgentToolResult:
        env = context.env
        path = params["path"]
        content = params["content"]
        get_or_throw(env.write_file(path, content))
        return AgentToolResult(
            content=[TextContent(text=f"已写入 {path}（{len(content)} 字符）")],
            details={},
        )

    return HarnessTool(
        name="write",
        description="创建或覆盖文件（自动创建父目录）。",
        parameters=WriteParams,
        execute=write,
    )
