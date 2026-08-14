from pi_agent.harness.session.types import MessageEntry, OperationStartedRecord, ToolStartedRecord
from pi_agent.types import TextContent, UserMessage


def test_message_entry():
    msg = UserMessage(content="hi", timestamp=0)
    entry = MessageEntry(message=msg, id="e1", seq=0)
    assert entry.type == "message"
    assert entry.message.content == "hi"


def test_operation_started_record():
    rec = OperationStartedRecord(
        id="op1", seq=0, lane="main", timestamp=0,
        source_leaf_id=None, intent={"kind": "run"},
    )
    assert rec.type == "operation_started"
    assert rec.intent["kind"] == "run"


def test_tool_started_record():
    rec = ToolStartedRecord(
        id="r1", seq=1, lane="main", timestamp=0,
        run_id="op1", assistant_entry_id="e1", tool_index=0,
        tool_call_id="c1", tool_name="read", effective_args={"path": "a.txt"},
        result_entry_id="e2", replay="never",
    )
    assert rec.type == "tool_started"
    assert rec.tool_name == "read"
