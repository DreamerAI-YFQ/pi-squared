"""
工具类型系统：定义 harness 层的工具类型和适配逻辑。

对应 pi 的工具系统。核心设计：
1. HarnessTool：工具定义，但不知道具体执行环境
2. ToolContext：执行上下文，包含 ExecutionEnv
3. bind_tool：把工具绑定到具体上下文，转换成 AgentTool

设计思想：
- 工具定义时不绑定环境（可复用）
- 执行时才注入具体环境（可替换）
- 适配层：把 HarnessTool 转换成 agent_loop 认识的 AgentTool

使用场景：
- 工具可以在不同环境中执行（本地、Docker、远程）
- 工具定义和执行环境解耦
- 支持动态切换执行环境
"""
from dataclasses import dataclass
from typing import Awaitable, Callable

from pydantic import BaseModel

from pi_agent.harness.env import ExecutionEnv
from pi_agent.types import AgentTool, AgentToolResult


@dataclass
class ToolContext:
    """工具执行上下文（对应 pi 的 ExecutionToolContext）。

    包含工具执行时需要的所有环境信息，目前主要是 ExecutionEnv。
    未来可以扩展添加其他上下文信息（如用户身份、权限、配置等）。

    Args:
        env: 执行环境（文件系统 + Shell 能力）
    """
    env: ExecutionEnv


@dataclass
class HarnessTool:
    """harness 层工具：execute 带 context（含 env），执行时才注入。

    对应 pi 的 AgentHarnessTool。与 AgentTool 的区别在于 execute 多一个
    context 参数，env 的绑定推迟到执行时。

    设计原因：
    - 工具定义时不绑定具体环境，可以在不同环境中复用
    - 支持动态切换执行环境（本地 → Docker → 远程）
    - 便于测试（可以注入 Mock 环境）

    Args:
        name: 工具名称（如 "read"、"write"、"bash"）
        description: 工具描述（用于给 LLM 理解工具用途）
        parameters: 参数类型（用 Pydantic BaseModel 定义，自动生成 JSON Schema）
        execute: 执行函数，接收 tool_call_id、参数字典、上下文，返回异步结果
        label: 工具标签（可选，用于分组或分类）
    """
    name: str
    description: str
    parameters: type[BaseModel]
    execute: Callable[[str, dict, ToolContext], Awaitable[AgentToolResult]]
    label: str = ""


def bind_tool(tool: HarnessTool, context: ToolContext) -> AgentTool:
    """把 harness 工具绑定到具体 context，适配成 agent_loop 认识的 AgentTool。

    对应 pi 组装层"把 AgentHarnessTool 绑定 context 转成 AgentTool"的适配步骤。

    这是一个适配器模式：
    - 输入：HarnessTool（需要 context）+ ToolContext（具体环境）
    - 输出：AgentTool（不需要 context，因为已经绑定）

    Args:
        tool: harness 层的工具定义
        context: 执行上下文（包含 ExecutionEnv）

    Returns:
        AgentTool：agent_loop 可以直接使用的工具
    """

    async def bound_execute(tool_call_id: str, params: dict) -> AgentToolResult:
        """绑定后的执行函数：context 已经捕获，调用时不需要再传。"""
        return await tool.execute(tool_call_id, params, context)

    return AgentTool(
        name=tool.name,
        description=tool.description,
        parameters=tool.parameters,
        execute=bound_execute,
        label=tool.label,
    )
