from dataclasses import dataclass
from typing import Literal, Union

from pi_agent.types import AgentToolResult, Message, ToolResultMessage


# ============ AgentEvent：agent 循环对外的通知 ============
# 用 dataclass 而非 pydantic：事件是"控制流通知"，不需要校验/序列化；
# 消息是"数据"才用 pydantic。
# dataclass 规则：有默认值的字段(type)必须排在无默认值字段之后，故 type 统一放最后。


@dataclass
class AgentStart:
    type: Literal["agent_start"] = "agent_start"


@dataclass
class AgentEnd:
    messages: list[Message]
    type: Literal["agent_end"] = "agent_end"


@dataclass
class TurnStart:
    type: Literal["turn_start"] = "turn_start"


@dataclass
class TurnEnd:
    message: Message
    toolResults: list[ToolResultMessage]
    type: Literal["turn_end"] = "turn_end"


@dataclass
class MessageStart:
    message: Message
    type: Literal["message_start"] = "message_start"


@dataclass
class MessageEnd:
    message: Message
    type: Literal["message_end"] = "message_end"


@dataclass
class ToolExecutionStart:
    toolCallId: str
    toolName: str
    args: dict
    type: Literal["tool_execution_start"] = "tool_execution_start"


@dataclass
class ToolExecutionEnd:
    toolCallId: str
    toolName: str
    result: AgentToolResult
    isError: bool
    type: Literal["tool_execution_end"] = "tool_execution_end"


AgentEvent = Union[
    AgentStart,
    AgentEnd,
    TurnStart,
    TurnEnd,
    MessageStart,
    MessageEnd,
    ToolExecutionStart,
    ToolExecutionEnd,
]
