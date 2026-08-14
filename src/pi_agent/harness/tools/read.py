from pydantic import BaseModel

from pi_agent.harness.result import get_or_throw
from pi_agent.harness.tools.types import HarnessTool, ToolContext
from pi_agent.types import AgentToolResult, TextContent


class ReadParams(BaseModel):
    path: str
    offset: int | None = None  # 1-indexed 起始行
    limit: int | None = None   # 最大读取行数


def create_read_tool() -> HarnessTool:
    """创建 read 工具（对应 pi 的 read.ts）。

    env 不在创建时绑定，而是在 execute 时通过 context 传入。
    """

    async def read(tool_call_id: str, params: dict, context: ToolContext) -> AgentToolResult:
        env = context.env
        path = params["path"]
        offset = params.get("offset")
        limit = params.get("limit")

        info = get_or_throw(env.file_info(path))
        if info.kind != "file":
            raise ValueError(f"不是文件: {path}")

        text = get_or_throw(env.read_text_file(path))
        all_lines = text.split("\n")
        start = max(0, (offset or 1) - 1)  # offset 是 1-indexed

        if start >= len(all_lines):
            raise ValueError(f"offset {offset} 超出文件末尾（共 {len(all_lines)} 行）")

        if limit is not None:
            end = min(start + limit, len(all_lines))
            selected = all_lines[start:end]
        else:
            selected = all_lines[start:]

        return AgentToolResult(content=[TextContent(text="\n".join(selected))], details={})

    return HarnessTool(
        name="read",
        description="读取文件内容，支持 offset（1-indexed 起始行）和 limit（最大行数）按行读取。",
        parameters=ReadParams,
        execute=read,
    )
