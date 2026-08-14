"""上下文压缩（对应 pi 的 compaction/compaction.ts 简化版）。

核心三问：何时压（should_compact）、切在哪（find_cut_point）、压成什么（generate_summary）。
"""
import json
import math
from dataclasses import dataclass

from pi_agent.types import AgentContext, Message, TextContent, UserMessage

SUMMARIZATION_SYSTEM_PROMPT = (
    "You are a context summarization assistant. Read the conversation and produce a "
    "structured summary. Do NOT continue the conversation, ONLY output the summary."
)

SUMMARIZATION_PROMPT = """Create a structured context checkpoint summary that another LLM will use to continue the work.

Use this EXACT format:

## Goal
[What is the user trying to accomplish?]

## Progress
### Done
- [x] [Completed tasks]

### In Progress
- [ ] [Current work]

## Key Decisions
- **[Decision]**: [Brief rationale]

## Next Steps
1. [Ordered list]

## Critical Context
- [Any data, file paths, or references needed to continue]

Keep each section concise. Preserve exact file paths, function names, and error messages."""


@dataclass
class CompactionSettings:
    enabled: bool = True
    reserve_tokens: int = 16384
    keep_recent_tokens: int = 20000


DEFAULT_COMPACTION_SETTINGS = CompactionSettings()


def estimate_tokens(message: Message) -> int:
    """估算单条消息的 token 数（字符数 / 4 的保守启发式）。"""
    chars = 0
    if message.role == "user":
        content = message.content
        if isinstance(content, str):
            chars = len(content)
        else:
            for block in content:
                if block.type == "text":
                    chars += len(block.text)
                elif block.type == "image":
                    chars += 4800
    elif message.role == "assistant":
        for block in message.content:
            if block.type == "text":
                chars += len(block.text)
            elif block.type == "toolCall":
                chars += len(block.name) + len(json.dumps(block.arguments))
    elif message.role == "toolResult":
        for block in message.content:
            if block.type == "text":
                chars += len(block.text)
    return math.ceil(chars / 4)


def estimate_context_tokens(messages: list[Message]) -> int:
    return sum(estimate_tokens(m) for m in messages)


def should_compact(context_tokens: int, context_window: int, settings: CompactionSettings) -> bool:
    """判断上下文是否超过压缩阈值。"""
    if not settings.enabled:
        return False
    return context_tokens > context_window - settings.reserve_tokens


def find_cut_point(messages: list[Message], keep_recent_tokens: int) -> int:
    """找压缩切点：从后往前累积 token，返回第一个保留的消息索引。"""
    accumulated = 0
    for i in range(len(messages) - 1, -1, -1):
        accumulated += estimate_tokens(messages[i])
        if accumulated >= keep_recent_tokens:
            return i
    return 0


def prepare_compaction(messages: list[Message], settings: CompactionSettings) -> tuple[list[Message], list[Message]]:
    """把消息分成「要压缩的历史」和「保留的尾部」。"""
    cut = find_cut_point(messages, settings.keep_recent_tokens)
    return messages[:cut], messages[cut:]


def _content_to_text(message: Message) -> str:
    parts = []
    for block in message.content if not isinstance(message.content, str) else []:
        if block.type == "text":
            parts.append(block.text)
    if isinstance(message.content, str):
        return message.content
    return "".join(parts)


def serialize_conversation(messages: list[Message]) -> str:
    """把消息列表序列化成文本（供摘要）。"""
    lines = []
    for m in messages:
        text = _content_to_text(m)
        lines.append(f"{m.role}: {text}")
    return "\n".join(lines)


async def generate_summary(messages: list[Message], stream_fn) -> str:
    """调用模型生成结构化摘要（stream_fn 注入）。"""
    conversation = serialize_conversation(messages)
    prompt = f"<conversation>\n{conversation}\n</conversation>\n\n{SUMMARIZATION_PROMPT}"
    context = AgentContext(
        systemPrompt=SUMMARIZATION_SYSTEM_PROMPT,
        messages=[UserMessage(content=prompt, timestamp=0)],
        tools=[],
    )
    response = await stream_fn(context)
    parts = [b.text for b in response.content if b.type == "text"]
    return "".join(parts)
