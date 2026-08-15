from pi_agent.harness.reducer import (
    RecordLogCorruption,
    RecordLogSlice,
    reduce_lane_state,
    validate_record_log,
)
from pi_agent.harness.session.types import (
    AbortRequestedRecord,
    MessageEntry,
    OperationFinishedRecord,
    OperationStartedRecord,
    WriteDeferredRecord,
)
from pi_agent.types import UserMessage


def _start(op_id: str, seq: int) -> OperationStartedRecord:
    return OperationStartedRecord(
        id=op_id, seq=seq, lane="main", timestamp=0,
        source_leaf_id=None, intent={"kind": "run"},
    )


def test_validate_multiple_open_operations():
    slice = RecordLogSlice(
        lane="main",
        open_operations=[_start("op1", 1), _start("op2", 2)],
        records=[],
        entries=[],
    )
    try:
        validate_record_log(slice)
        assert False, "应该抛 corruption"
    except RecordLogCorruption as e:
        assert e.reason == "multiple_open_operations"


def test_validate_unknown_operation():
    record = AbortRequestedRecord(id="r1", seq=1, lane="main", timestamp=0, run_id="missing")
    slice = RecordLogSlice(lane="main", open_operations=[], records=[record], entries=[])
    try:
        validate_record_log(slice)
        assert False, "应该抛 corruption"
    except RecordLogCorruption as e:
        assert e.reason == "unknown_operation"


def test_reduce_idle_lane():
    slice = RecordLogSlice(lane="main", open_operations=[], records=[], entries=[])
    state = reduce_lane_state(slice)
    assert state.operation is None


def test_reduce_active_aborting():
    start = _start("op1", 1)
    abort = AbortRequestedRecord(id="r2", seq=2, lane="main", timestamp=0, run_id="op1")
    slice = RecordLogSlice(
        lane="main",
        open_operations=[start],
        records=[start, abort],
        entries=[],
    )
    state = reduce_lane_state(slice)
    assert state.operation is not None
    assert state.operation["aborting"] is True


def _user_entry(entry_id: str, seq: int, parent_id: str | None) -> MessageEntry:
    return MessageEntry(
        message=UserMessage(role="user", content="hi", timestamp=0),
        id=entry_id, seq=seq, parent_id=parent_id, timestamp=0,
    )


def _deferred(seq: int, entry_id: str, parent_id: str | None) -> WriteDeferredRecord:
    return WriteDeferredRecord(
        id=f"wd{seq}", seq=seq, lane="main", timestamp=0, run_id="op1",
        target={"entry": {"id": entry_id, "parent_id": parent_id}},
    )


def test_validate_provisioned_match():
    start = _start("op1", 1)
    deferred = _deferred(2, "e1", "p1")
    entry = _user_entry("e1", 3, "p1")
    slice = RecordLogSlice(lane="main", open_operations=[], records=[start, deferred], entries=[entry])
    validate_record_log(slice)  # 匹配：不抛


def test_validate_provisioned_mismatch():
    start = _start("op1", 1)
    deferred = _deferred(2, "e1", "p1")
    entry = _user_entry("e1", 3, "OTHER")
    slice = RecordLogSlice(lane="main", open_operations=[], records=[start, deferred], entries=[entry])
    try:
        validate_record_log(slice)
        assert False, "应该抛 corruption"
    except RecordLogCorruption as e:
        assert e.reason == "provisioned_entry_mismatch"


def test_validate_provisioned_pending():
    """deferred 尚未完成（entry 未写入）是合法状态。"""
    start = _start("op1", 1)
    deferred = _deferred(2, "e1", "p1")
    slice = RecordLogSlice(lane="main", open_operations=[], records=[start, deferred], entries=[])
    validate_record_log(slice)  # 未写入：不抛


def test_validate_write_deferred_without_target():
    start = _start("op1", 1)
    deferred = WriteDeferredRecord(
        id="wd2", seq=2, lane="main", timestamp=0, run_id="op1", target={},
    )
    slice = RecordLogSlice(lane="main", open_operations=[], records=[start, deferred], entries=[])
    try:
        validate_record_log(slice)
        assert False, "应该抛 corruption"
    except RecordLogCorruption as e:
        assert e.reason == "invalid_deferred_handle"
