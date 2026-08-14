import asyncio

from pi_agent.streaming.event_stream import EventStream, create_assistant_message_stream
from pi_agent.types import AssistantMessage, StreamDone, TextContent, TextDelta


def test_event_stream_push_and_consume():
    stream = EventStream(
        is_complete=lambda e: e == "done",
        extract_result=lambda e: "FINAL",
    )
    stream.push("a")
    stream.push("b")
    stream.push("done")

    async def consume():
        return [e async for e in stream]

    events = asyncio.run(consume())
    assert events == ["a", "b", "done"]
    assert stream.final_result == "FINAL"


def test_event_stream_ignore_after_done():
    stream = EventStream(
        is_complete=lambda e: e == "done",
        extract_result=lambda e: "FINAL",
    )
    stream.push("a")
    stream.push("done")
    stream.push("b")  # 终结后应被忽略

    async def consume():
        return [e async for e in stream]

    events = asyncio.run(consume())
    assert events == ["a", "done"]


def test_assistant_message_stream():
    stream = create_assistant_message_stream()
    stream.push(TextDelta(delta="hi"))
    message = AssistantMessage(content=[TextContent(text="hi")], stopReason="stop", timestamp=0)
    stream.push(StreamDone(message=message))

    async def consume():
        return [e async for e in stream]

    events = asyncio.run(consume())
    assert len(events) == 2
    assert stream.final_result is not None
    assert stream.final_result.stopReason == "stop"
