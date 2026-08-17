from dataclasses import dataclass
from typing import Literal, Union

from pi_agent.types import AgentToolResult, Message, ToolResultMessage


# ============ AgentEvent：agent 循环对外的通知 ============
# 用 dataclass 而非 pydantic：事件是"控制流通知"，不需要校验/序列化；
# 消息是"数据"才用 pydantic。
# dataclass 规则：有默认值的字段(type)必须排在无默认值字段之后，故 type 统一放最后。


@dataclass
class AgentStart: # 代理开始事件
    type: Literal["agent_start"] = "agent_start"


@dataclass
class AgentEnd: # 代理结束事件
    messages: list[Message]
    type: Literal["agent_end"] = "agent_end"


@dataclass
class TurnStart: # 回合开始事件
    type: Literal["turn_start"] = "turn_start"


@dataclass
class TurnEnd: # 回合结束事件
    message: Message
    toolResults: list[ToolResultMessage]
    type: Literal["turn_end"] = "turn_end"


@dataclass
class MessageStart: # 消息开始事件
    message: Message
    type: Literal["message_start"] = "message_start"


@dataclass
class MessageEnd: # 消息结束事件
    message: Message
    type: Literal["message_end"] = "message_end"


@dataclass
class ToolExecutionStart: # 工具执行开始事件
    toolCallId: str
    toolName: str
    args: dict
    type: Literal["tool_execution_start"] = "tool_execution_start"


@dataclass
class ToolExecutionEnd: # 工具执行结束事件      
    toolCallId: str
    toolName: str
    result: AgentToolResult
    isError: bool
    type: Literal["tool_execution_end"] = "tool_execution_end"


AgentEvent = Union[ # 代理事件类型，联合类型
    AgentStart,
    AgentEnd,
    TurnStart,
    TurnEnd,
    MessageStart,
    MessageEnd,
    ToolExecutionStart,
    ToolExecutionEnd,
]
