from pi_agent.harness.session.state import EntryMutation, RecordMutation, SessionError, SessionState
from pi_agent.harness.session.types import (
    MessageEntry,
    OperationFinishedRecord,
    OperationStartedRecord,
)
from pi_agent.types import UserMessage


def _msg_entry(seq: int, entry_id: str, content: str, parent_id: str | None = None) -> MessageEntry:
    return MessageEntry(
        message=UserMessage(content=content, timestamp=0),
        id=entry_id, seq=seq, parent_id=parent_id,
    )


def test_append_entries():
    state = SessionState()
    state.apply_mutation(EntryMutation(entry=_msg_entry(1, "e1", "hi"), lane="main"))
    state.apply_mutation(EntryMutation(entry=_msg_entry(2, "e2", "there", parent_id="e1"), lane="main"))

    assert len(state.find_entries()) == 2
    assert state.get_stats().message_count == 2


def test_non_consecutive_seq_raises():
    state = SessionState()
    try:
        state.apply_mutation(EntryMutation(entry=_msg_entry(5, "e1", "hi"), lane="main"))
        assert False, "应该抛异常"
    except SessionError as e:
        assert e.code == "invalid_entry"


def test_duplicate_id_raises():
    state = SessionState()
    state.apply_mutation(EntryMutation(entry=_msg_entry(1, "e1", "hi"), lane="main"))
    try:
        state.apply_mutation(EntryMutation(entry=_msg_entry(2, "e1", "dup"), lane="main"))
        assert False, "应该抛异常"
    except SessionError as e:
        assert e.code == "already_exists"


def test_open_operations():
    state = SessionState()
    start = OperationStartedRecord(
        id="op1", seq=1, lane="main", timestamp=0,
        source_leaf_id=None, intent={"kind": "run"},
    )
    state.apply_mutation(RecordMutation(record=start))
    assert len(state.find_open_operations("main")) == 1

    finish = OperationFinishedRecord(
        id="r2", seq=2, lane="main", timestamp=0, run_id="op1", outcome="completed",
    )
    state.apply_mutation(RecordMutation(record=finish))
    assert len(state.find_open_operations("main")) == 0
