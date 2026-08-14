from pi_agent.streaming.tool_call import ToolCallAccumulator


def test_accumulate_two_deltas():
    acc = ToolCallAccumulator(tool_call_id="c1", name="read")
    acc.add_delta('{"path":')
    # 第一段残缺，解析不出任何参数
    assert acc.arguments == {}

    acc.add_delta('"a.txt"}')
    assert acc.arguments == {"path": "a.txt"}

    tool_call = acc.finalize()
    assert tool_call.id == "c1"
    assert tool_call.name == "read"
    assert tool_call.arguments == {"path": "a.txt"}


def test_single_complete_delta():
    acc = ToolCallAccumulator(tool_call_id="c2", name="write")
    acc.add_delta('{"path":"b.txt"}')
    tool_call = acc.finalize()
    assert tool_call.arguments == {"path": "b.txt"}
