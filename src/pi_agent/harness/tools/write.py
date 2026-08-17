"""
write 工具：写入文件内容。

对应 pi 的 write.ts。让 Agent 能够创建新文件或覆盖旧文件。

核心功能：
- 创建新文件（自动创建父目录）
- 覆盖已有文件
- 支持任意文本内容
- 错误处理：通过 Result 类型显式处理失败

使用场景：
- Agent 需要创建新的代码文件
- Agent 需要修改配置文件（完全覆盖）
- Agent 需要生成测试文件或文档
"""
from pydantic import BaseModel

from pi_agent.harness.result import get_or_throw
from pi_agent.harness.tools.types import HarnessTool, ToolContext
from pi_agent.types import AgentToolResult, TextContent


class WriteParams(BaseModel):
    """write 工具的参数类型。

    Args:
        path: 文件路径（如果父目录不存在会自动创建）
        content: 文件内容（任意文本）
    """
    path: str
    content: str


def create_write_tool() -> HarnessTool:
    """创建 write 工具（对应 pi 的 write.ts）。

    env 不在创建时绑定，而是在 execute 时通过 context 传入。
    这样同一个工具可以在不同环境中使用（本地、Docker、远程）。

    Returns:
        HarnessTool: 可以被绑定到环境的工具定义
    """

    async def write(tool_call_id: str, params: dict, context: ToolContext) -> AgentToolResult:
        """执行写入操作。

        Args:
            tool_call_id: 工具调用ID（用于追踪）
            params: 参数字典（path、content）
            context: 执行上下文（包含 env）

        Returns:
            AgentToolResult: 包含写入确认信息的执行结果
        """
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
