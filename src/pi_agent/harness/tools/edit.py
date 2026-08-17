"""
edit 工具：精确替换文件内容。

对应 pi 的 edit.ts 的简化版。让 Agent 能够对文件做精确的文本替换。

核心功能：
- 精确替换文本（old_text 必须在文件中唯一）
- 支持批量替换（一次多个替换操作）
- 错误检查：确保 old_text 存在且唯一
- 错误处理：通过 Result 类型显式处理失败

使用场景：
- Agent 需要修改代码中的某段函数
- Agent 需要更新配置文件中的某个值
- Agent 需要修复代码中的 bug（精确替换）
"""
from pydantic import BaseModel

from pi_agent.harness.result import get_or_throw
from pi_agent.harness.tools.types import HarnessTool, ToolContext
from pi_agent.types import AgentToolResult, TextContent


class ReplaceEdit(BaseModel):
    """单个替换操作。

    Args:
        old_text: 要被替换的文本（必须在文件中唯一）
        new_text: 替换后的文本
    """
    old_text: str
    new_text: str


class EditParams(BaseModel):
    """edit 工具的参数类型。

    Args:
        path: 文件路径
        edits: 替换操作列表（按顺序执行）
    """
    path: str
    edits: list[ReplaceEdit]


def create_edit_tool() -> HarnessTool:
    """创建 edit 工具（对应 pi 的 edit.ts 的简化版：精确替换）。

    env 不在创建时绑定，而是在 execute 时通过 context 传入。
    这样同一个工具可以在不同环境中使用（本地、Docker、远程）。

    Returns:
        HarnessTool: 可以被绑定到环境的工具定义
    """

    async def edit(tool_call_id: str, params: dict, context: ToolContext) -> AgentToolResult:
        """执行编辑操作。

        Args:
            tool_call_id: 工具调用ID（用于追踪）
            params: 参数字典（path、edits）
            context: 执行上下文（包含 env）

        Returns:
            AgentToolResult: 包含编辑确认信息的执行结果

        Raises:
            ValueError: 如果 old_text 不存在或出现多次
        """
        env = context.env
        path = params["path"]
        edits = params["edits"]

        # 检查文件类型
        info = get_or_throw(env.file_info(path))
        if info.kind != "file":
            raise ValueError(f"不是文件: {path}")

        # 读取文件内容
        content = get_or_throw(env.read_text_file(path))

        # 执行每个替换操作
        for edit in edits:
            old_text = edit["old_text"]
            new_text = edit["new_text"]
            count = content.count(old_text)
            if count == 0:
                raise ValueError(f"未找到要替换的文本: {old_text[:50]!r}")
            if count > 1:
                raise ValueError(f"要替换的文本不唯一（出现 {count} 次）: {old_text[:50]!r}")
            content = content.replace(old_text, new_text, 1)

        # 写回文件
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
