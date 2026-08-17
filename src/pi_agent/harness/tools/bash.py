"""
bash 工具：执行 shell 命令。

对应 pi 的 bash.ts 的简化版。让 Agent 能够执行系统命令。

核心功能：
- 执行任意 shell 命令
- 返回 stdout、stderr 和退出码
- 支持超时控制
- 错误处理：通过 Result 类型显式处理失败

使用场景：
- Agent 需要运行 git 命令（git status、git commit）
- Agent 需要安装依赖（npm install、pip install）
- Agent 需要运行测试（pytest、npm test）
- Agent 需要启动服务（npm start、python app.py）
"""
from pydantic import BaseModel

from pi_agent.harness.result import get_or_throw
from pi_agent.harness.tools.types import HarnessTool, ToolContext
from pi_agent.types import AgentToolResult, TextContent


class BashParams(BaseModel):
    """bash 工具的参数类型。

    Args:
        command: 要执行的 shell 命令（字符串，会通过 shell=True 传给 subprocess）
        timeout: 超时时间（秒），超时则抛异常
    """
    command: str
    timeout: float | None = None


def create_bash_tool() -> HarnessTool:
    """创建 bash 工具（对应 pi 的 bash.ts 的简化版）。

    env 不在创建时绑定，而是在 execute 时通过 context 传入。
    这样同一个工具可以在不同环境中使用（本地、Docker、远程）。

    Returns:
        HarnessTool: 可以被绑定到环境的工具定义
    """

    async def bash(tool_call_id: str, params: dict, context: ToolContext) -> AgentToolResult:
        """执行命令操作。

        Args:
            tool_call_id: 工具调用ID（用于追踪）
            params: 参数字典（command、timeout）
            context: 执行上下文（包含 env）

        Returns:
            AgentToolResult: 包含命令执行结果的执行结果（stdout + stderr + 退出码）
        """
        env = context.env
        command = params["command"]
        timeout = params.get("timeout")

        # 执行命令
        result = get_or_throw(env.exec(command, timeout=timeout))

        # 组合输出（stdout + stderr + 退出码）
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
