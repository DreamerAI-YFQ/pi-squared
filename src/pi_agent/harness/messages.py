from dataclasses import dataclass
from typing import Literal, Union

from pi_agent.types import Message, UserMessage


@dataclass
class CustomMessage:
    """内部自定义消息：不直接给 LLM，需经 convert_to_llm 转换。"""
    role: Literal["custom"] = "custom"
    content: str = ""
    timestamp: int = 0


AgentMessage = Union[Message, CustomMessage]


def convert_to_llm(messages: list[AgentMessage]) -> list[Message]:
    """把 AgentMessage（含自定义消息）转换成标准 LLM 消息。

    - 标准消息（user/assistant/toolResult）原样保留
    - CustomMessage 转成 UserMessage（content 作为文本）
    """
    result: list[Message] = []
    for msg in messages:
        if isinstance(msg, CustomMessage):
            result.append(UserMessage(content=msg.content, timestamp=msg.timestamp))
        else:
            result.append(msg)
    return result


def create_compaction_summary_message(summary: str, tokens_before: int, timestamp: int) -> UserMessage:
    """把压缩摘要包装成 UserMessage（对应 pi 的 createCompactionSummaryMessage）。"""
    return UserMessage(content=f"<compaction_summary>\n{summary}\n</compaction_summary>", timestamp=timestamp)


def create_branch_summary_message(summary: str, from_id: str, timestamp: int) -> UserMessage:
    """把分支摘要包装成 UserMessage（对应 pi 的 createBranchSummaryMessage）。"""
    return UserMessage(content=f"<branch_summary>\n{summary}\n</branch_summary>", timestamp=timestamp)
