"""
read 工具：读取文件内容。

对应 pi 的 read.ts。让 Agent 能够读取代码文件、配置文件、日志等。

核心功能：
- 支持按行读取（offset + limit）
- 支持读取完整文件
- 自动检查文件类型（必须是普通文件）
- 错误处理：通过 Result 类型显式处理失败

使用场景：
- Agent 需要查看代码文件
- Agent 需要检查配置文件
- Agent 需要读取日志或测试结果
"""
from pydantic import BaseModel

from pi_agent.harness.result import get_or_throw
from pi_agent.harness.tools.types import HarnessTool, ToolContext
from pi_agent.types import AgentToolResult, TextContent


class ReadParams(BaseModel):
    """read 工具的参数类型。

    Args:
        path: 文件路径
        offset: 起始行号（1-indexed，从第几行开始读）
        limit: 最大读取行数（读多少行）
    """
    path: str
    offset: int | None = None  # 1-indexed 起始行
    limit: int | None = None   # 最大读取行数


def create_read_tool() -> HarnessTool:
    """创建 read 工具（对应 pi 的 read.ts）。

    env 不在创建时绑定，而是在 execute 时通过 context 传入。
    这样同一个工具可以在不同环境中使用（本地、Docker、远程）。

    Returns:
        HarnessTool: 可以被绑定到环境的工具定义
    """

    async def read(tool_call_id: str, params: dict, context: ToolContext) -> AgentToolResult:
        """执行读取操作。

        Args:
            tool_call_id: 工具调用ID（用于追踪）
            params: 参数字典（path、offset、limit）
            context: 执行上下文（包含 env）

        Returns:
            AgentToolResult: 包含文件内容的执行结果

        Raises:
            ValueError: 如果路径不是文件、offset 超出范围等
        """
        env = context.env
        path = params["path"]
        offset = params.get("offset")
        limit = params.get("limit")

        # 检查文件类型
        info = get_or_throw(env.file_info(path))
        if info.kind != "file":
            raise ValueError(f"不是文件: {path}")

        # 读取文件内容
        text = get_or_throw(env.read_text_file(path))
        all_lines = text.split("\n")
        start = max(0, (offset or 1) - 1)  # offset 是 1-indexed，转为 0-indexed

        # 检查 offset 是否超出范围
        if start >= len(all_lines):
            raise ValueError(f"offset {offset} 超出文件末尾（共 {len(all_lines)} 行）")

        # 按 limit 截取行
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
