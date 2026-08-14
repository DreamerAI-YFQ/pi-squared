from pi_agent.extensions.observability import Observability


def test_record_llm_and_cost():
    obs = Observability()
    obs.record_llm("deepseek-chat", tokens=100, cost=0.01)
    obs.record_llm("deepseek-chat", tokens=50, cost=0.005)

    assert obs.total_tokens == 150
    assert abs(obs.total_cost - 0.015) < 1e-9
    assert len(obs.llm_calls()) == 2


def test_record_tool():
    obs = Observability()
    obs.record_tool("read", is_error=False)
    obs.record_tool("bash", is_error=True)

    assert len(obs.tool_calls()) == 2
    assert obs.tool_calls()[1]["isError"] is True


def test_span_tree():
    obs = Observability()
    obs.start_span("agent")
    obs.start_span("turn")
    obs.start_span("tool", tool="write")
    obs.end_span()  # tool
    obs.end_span()  # turn
    obs.end_span()  # agent

    spans = obs.spans
    assert len(spans) == 1
    assert spans[0]["name"] == "agent"
    turn = spans[0]["children"][0]
    assert turn["name"] == "turn"
    tool = turn["children"][0]
    assert tool["name"] == "tool"
    assert tool["attrs"]["tool"] == "write"
    assert "duration_ms" in tool
