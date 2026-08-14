from pi_agent.streaming.sse import parse_sse


def test_single_event():
    events = list(parse_sse('data: {"a":1}\n\n'))
    assert events == [(None, '{"a":1}')]


def test_multiline_data():
    events = list(parse_sse("data: line1\ndata: line2\n\n"))
    assert events == [(None, "line1\nline2")]


def test_event_field():
    events = list(parse_sse("event: message\ndata: hello\n\n"))
    assert events == [("message", "hello")]


def test_comment_and_multiple_events():
    text = ": 这是注释\ndata: first\n\ndata: second\n\n"
    events = list(parse_sse(text))
    assert events == [(None, "first"), (None, "second")]


def test_crlf_line_endings():
    events = list(parse_sse("data: hello\r\n\r\n"))
    assert events == [(None, "hello")]


def test_trailing_without_blank_line():
    events = list(parse_sse("data: no-trailing-newline"))
    assert events == [(None, "no-trailing-newline")]
