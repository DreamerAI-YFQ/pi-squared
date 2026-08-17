"""
会话上下文还原（对应 pi 的 harness/session/context.ts）。

把持久化的 Entry 序列还原成 LLM 上下文（AgentMessage[]）。
这是"恢复会话"的关键：从 entry 重放出模型能看的消息列表。

设计目标：
1. 把对话历史从 Entry 格式转换成 LLM 能理解的 Message 格式
2. 处理特殊的 Entry 类型（压缩摘要、分支摘要）
3. 过滤不应该进入上下文的消息（如 deferred 消息）

核心问题：
- Entry 是持久化格式（包含各种元数据）
- LLM 只需要看 Message 格式（role + content）
- 需要转换和过滤

类比：
- Entry = 日记条目（详细记录）
- LLM 上下文 = 给 AI 看的摘要（精简信息）
- 这个函数 = 从日记里提取 AI 需要的信息
"""
from pi_agent.harness.messages import create_branch_summary_message, create_compaction_summary_message
from pi_agent.harness.session.types import Entry
from pi_agent.types import Message


def session_entry_to_context_messages(entry: Entry) -> list[Message]:
    """把单个 entry 还原成上下文消息列表。

    根据 Entry 类型进行不同的处理：
    - message：直接转成消息（但 deferred 的 assistant 消息不进上下文）
    - compaction：生成压缩摘要消息 + 保留的尾部消息
    - branch_summary：生成分支摘要消息
    - 其他类型：不生成消息

    Args:
        entry: Entry 对象

    Returns:
        Message 列表（可能为空）
    """
    if entry.type == "message":
        # 普通消息：直接转成 Message
        # 但 assistant 的 deferred 消息不进入上下文（等待异步结果）
        if entry.message.role == "assistant" and getattr(entry.message, "stopReason", None) == "deferred":
            return []  # deferred 消息不进上下文
        return [entry.message]

    if entry.type == "compaction":
        # 压缩摘要：生成压缩摘要消息 + 保留的尾部消息
        return [
            create_compaction_summary_message(entry.summary, entry.tokens_before, entry.timestamp),
            *entry.retained_tail,  # 保留的尾部消息（不压缩的部分）
        ]

    if entry.type == "branch_summary":
        # 分支摘要：生成分支摘要消息
        return [create_branch_summary_message(entry.summary, entry.from_id, entry.timestamp)]

    # 其他类型（model_change、thinking_level_change 等）不生成消息
    return []


def build_session_context(entries: list[Entry]) -> list[Message]:
    """把 entry 序列还原成 LLM 上下文消息列表。

    遍历所有 Entry，转换成 Message，合并成完整的上下文。

    Args:
        entries: Entry 列表（按顺序）

    Returns:
        Message 列表（LLM 能理解的上下文）
    """
    messages: list[Message] = []
    for entry in entries:
        messages.extend(session_entry_to_context_messages(entry))
    return messages
