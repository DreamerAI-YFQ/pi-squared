from pi_agent.harness.session.context import build_session_context
from pi_agent.harness.session.types import MessageEntry
from pi_agent.types import AssistantMessage, TextContent, UserMessage


def test_build_session_context_from_messages():
    entries = [
        MessageEntry(message=UserMessage(content="hi", timestamp=0), id="e1", seq=1),
        MessageEntry(
            message=AssistantMessage(content=[TextContent(text="hello")], stopReason="stop", timestamp=0),
            id="e2", seq=2, parent_id="e1",
        ),
    ]

    messages = build_session_context(entries)
    assert [m.role for m in messages] == ["user", "assistant"]


def test_deferred_assistant_dropped():
    entries = [
        MessageEntry(
            message=AssistantMessage(content=[], stopReason="deferred", timestamp=0),
            id="e1", seq=1,
        ),
    ]
    assert build_session_context(entries) == []
