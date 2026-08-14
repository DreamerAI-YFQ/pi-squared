from pi_agent.harness.compaction import (
    DEFAULT_COMPACTION_SETTINGS,
    estimate_context_tokens,
    estimate_tokens,
    find_cut_point,
    prepare_compaction,
    should_compact,
)
from pi_agent.types import TextContent, ToolCall, UserMessage


def _user(text: str) -> UserMessage:
    return UserMessage(content=text, timestamp=0)


def test_estimate_tokens_text():
    # 4 个字符 ≈ 1 token
    assert estimate_tokens(_user("hello")) == 2  # ceil(5/4) = 2


def test_estimate_tokens_tool_call():
    from pi_agent.types import AssistantMessage
    msg = AssistantMessage(
        content=[ToolCall(id="c1", name="read", arguments={"path": "a.txt"})],
        stopReason="toolUse", timestamp=0,
    )
    # name(4) + json({"path": "a.txt"})(约18) = 22 字符 / 4 ≈ 6
    assert estimate_tokens(msg) > 0


def test_should_compact():
    settings = DEFAULT_COMPACTION_SETTINGS
    # 超阈值：context_window 10000, reserve 16384 时永远为 False（窗口太小）
    # 用合理窗口测试
    assert should_compact(50000, 64000, settings) is True   # 50000 > 64000-16384
    assert should_compact(10000, 64000, settings) is False  # 10000 < 64000-16384


def test_prepare_compaction_splits():
    messages = [_user(f"消息{i}") for i in range(100)]
    # keep_recent_tokens 很小，切点应该在靠后
    to_summarize, retained = prepare_compaction(messages, DEFAULT_COMPACTION_SETTINGS)
    assert len(to_summarize) + len(retained) == 100


def test_estimate_context_tokens():
    messages = [_user("hello"), _user("world")]
    total = estimate_context_tokens(messages)
    assert total == estimate_tokens(messages[0]) + estimate_tokens(messages[1])
