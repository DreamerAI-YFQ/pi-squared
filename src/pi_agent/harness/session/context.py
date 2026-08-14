"""会话上下文还原（对应 pi 的 harness/session/context.ts）。

把持久化的 Entry 序列还原成 LLM 上下文（AgentMessage[]）。
这是"恢复会话"的关键：从 entry 重放出模型能看的消息列表。
"""
from pi_agent.harness.messages import create_branch_summary_message, create_compaction_summary_message
from pi_agent.harness.session.types import Entry
from pi_agent.types import Message


def session_entry_to_context_messages(entry: Entry) -> list[Message]:
    """把单个 entry 还原成上下文消息列表。"""
    if entry.type == "message":
        # assistant 的 deferred 消息不进入上下文（等待异步结果）
        if entry.message.role == "assistant" and getattr(entry.message, "stopReason", None) == "deferred":
            return []
        return [entry.message]
    if entry.type == "compaction":
        return [
            create_compaction_summary_message(entry.summary, entry.tokens_before, entry.timestamp),
            *entry.retained_tail,
        ]
    if entry.type == "branch_summary":
        return [create_branch_summary_message(entry.summary, entry.from_id, entry.timestamp)]
    return []


def build_session_context(entries: list[Entry]) -> list[Message]:
    """把 entry 序列还原成 LLM 上下文消息列表。"""
    messages: list[Message] = []
    for entry in entries:
        messages.extend(session_entry_to_context_messages(entry))
    return messages
