from dataclasses import dataclass
from typing import Awaitable, Callable

from pydantic import BaseModel

from pi_agent.harness.env import ExecutionEnv
from pi_agent.types import AgentTool, AgentToolResult


@dataclass
class ToolContext:
    """工具执行上下文（对应 pi 的 ExecutionToolContext）。"""
    env: ExecutionEnv


@dataclass
class HarnessTool:
    """harness 层工具：execute 带 context（含 env），执行时才注入。

    对应 pi 的 AgentHarnessTool。与 AgentTool 的区别在于 execute 多一个
    context 参数，env 的绑定推迟到执行时。
    """
    name: str
    description: str
    parameters: type[BaseModel]
    execute: Callable[[str, dict, ToolContext], Awaitable[AgentToolResult]]
    label: str = ""


def bind_tool(tool: HarnessTool, context: ToolContext) -> AgentTool:
    """把 harness 工具绑定到具体 context，适配成 agent_loop 认识的 AgentTool。

    对应 pi 组装层"把 AgentHarnessTool 绑定 context 转成 AgentTool"的适配步骤。
    """

    async def bound_execute(tool_call_id: str, params: dict) -> AgentToolResult:
        return await tool.execute(tool_call_id, params, context)

    return AgentTool(
        name=tool.name,
        description=tool.description,
        parameters=tool.parameters,
        execute=bound_execute,
        label=tool.label,
    )
