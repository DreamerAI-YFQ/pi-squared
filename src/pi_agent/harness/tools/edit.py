from pydantic import BaseModel

from pi_agent.harness.result import get_or_throw
from pi_agent.harness.tools.types import HarnessTool, ToolContext
from pi_agent.types import AgentToolResult, TextContent


class ReplaceEdit(BaseModel):
    old_text: str
    new_text: str


class EditParams(BaseModel):
    path: str
    edits: list[ReplaceEdit]


def create_edit_tool() -> HarnessTool:
    """创建 edit 工具（对应 pi 的 edit.ts 的简化版：精确替换）。"""

    async def edit(tool_call_id: str, params: dict, context: ToolContext) -> AgentToolResult:
        env = context.env
        path = params["path"]
        edits = params["edits"]

        info = get_or_throw(env.file_info(path))
        if info.kind != "file":
            raise ValueError(f"不是文件: {path}")

        content = get_or_throw(env.read_text_file(path))

        for edit in edits:
            old_text = edit["old_text"]
            new_text = edit["new_text"]
            count = content.count(old_text)
            if count == 0:
                raise ValueError(f"未找到要替换的文本: {old_text[:50]!r}")
            if count > 1:
                raise ValueError(f"要替换的文本不唯一（出现 {count} 次）: {old_text[:50]!r}")
            content = content.replace(old_text, new_text, 1)

        get_or_throw(env.write_file(path, content))
        return AgentToolResult(
            content=[TextContent(text=f"已编辑 {path}（{len(edits)} 处替换）")],
            details={},
        )

    return HarnessTool(
        name="edit",
        description="对文件做精确替换。edits 是替换列表，每个 edit 的 old_text 必须在文件中唯一。",
        parameters=EditParams,
        execute=edit,
    )
