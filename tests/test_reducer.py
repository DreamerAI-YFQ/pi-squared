from pi_agent.harness.reducer import (
    RecordLogCorruption,
    RecordLogSlice,
    reduce_lane_state,
    validate_record_log,
)
from pi_agent.harness.session.types import (
    AbortRequestedRecord,
    OperationFinishedRecord,
    OperationStartedRecord,
)


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
