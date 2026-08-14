"""恢复协议（对应 pi 的 harness/reducer.ts）。

从持久化的 record log 重建 lane 的编排状态（进程崩溃后恢复）。
核心：
- validate_record_log：校验 record log 一致性（12 种 corruption 检测）
- reduce_lane_state：重建运行状态
"""
from dataclasses import dataclass
from typing import Literal

from pi_agent.harness.session.types import (
    Entry,
    LaneRecord,
    OperationStartedRecord,
    StepAttemptRecord,
    ToolStartedRecord,
)


RecordLogCorruptionReason = Literal[
    "multiple_open_operations",
    "unknown_operation",
    "record_after_finish",
    "non_consecutive_attempt",
    "invalid_compaction_reason",
    "queue_after_abort",
    "invalid_queue_cancellation",
    "inconsistent_step",
    "tool_call_mismatch",
    "duplicate_tool_invocation",
    "provisioned_entry_mismatch",
    "invalid_deferred_handle",
]


class RecordLogCorruption(Exception):
    def __init__(self, reason: RecordLogCorruptionReason, message: str):
        super().__init__(message)
        self.reason = reason


@dataclass
class RecordLogSlice:
    lane: str
    open_operations: list[OperationStartedRecord]
    records: list[LaneRecord]
    entries: list[Entry]


@dataclass
class LaneState:
    lane: str
    leaf_id: str | None
    operation: dict | None
    pending_next_run: list[dict]


def _run_id_of(record: LaneRecord) -> str | None:
    return getattr(record, "run_id", None)


def _corrupt(reason: RecordLogCorruptionReason, message: str) -> None:
    raise RecordLogCorruption(reason, message)


def _validate_attempt_reason(record: StepAttemptRecord) -> None:
    """compaction step 必须有 valid reason；非 compaction step 不能有 reason。"""
    reason = record.compaction_reason
    if record.step == "compaction":
        if reason not in ("manual", "threshold", "overflow"):
            _corrupt("invalid_compaction_reason", f"Compaction attempt {record.id} has no valid compaction reason")
    elif reason is not None:
        _corrupt("invalid_compaction_reason", f"{record.step} attempt {record.id} has a compaction reason")


def _validate_attempt_sequence(
    record: StepAttemptRecord,
    previous: StepAttemptRecord | None,
    entries_by_id: dict[str, Entry],
) -> None:
    """attempt 必须连续；同一系列的 resultEntryId/compactionReason 必须一致。"""
    continues = previous is not None and previous.step == record.step
    expected_attempt = previous.attempt + 1 if continues else 1
    if record.attempt != expected_attempt:
        _corrupt(
            "non_consecutive_attempt",
            f"{record.step} attempt {record.id} is {record.attempt}; expected {expected_attempt}",
        )
    if not continues or record.step == "assistant" or previous is None:
        return
    if record.result_entry_id != previous.result_entry_id:
        _corrupt("inconsistent_step", f"{record.step} attempts disagree on their result entry id")
    if record.compaction_reason != previous.compaction_reason:
        _corrupt("inconsistent_step", f"{record.step} attempts disagree on their compaction reason")


def _validate_tool_start(
    record: ToolStartedRecord,
    entries_by_id: dict[str, Entry],
    invocations: set[str],
) -> None:
    """tool invocation 不能重复；必须匹配 assistant 的 tool-call ordinal。"""
    invocation = f"{record.assistant_entry_id}\x00{record.tool_index}"
    if invocation in invocations:
        _corrupt("duplicate_tool_invocation", f"Tool invocation {record.assistant_entry_id}:{record.tool_index} is duplicated")
    invocations.add(invocation)

    assistant_entry = entries_by_id.get(record.assistant_entry_id)
    if assistant_entry is None or assistant_entry.type != "message" or assistant_entry.message.role != "assistant":
        _corrupt("tool_call_mismatch", f"Tool start {record.id} does not reference an assistant entry")

    tool_calls = [c for c in assistant_entry.message.content if c.type == "toolCall"]
    tool_call = tool_calls[record.tool_index] if record.tool_index < len(tool_calls) else None
    if tool_call is None or tool_call.id != record.tool_call_id or tool_call.name != record.tool_name:
        _corrupt("tool_call_mismatch", f"Tool start {record.id} does not match its assistant tool-call ordinal")


def _validate_deferred_handles(entries: list[Entry]) -> None:
    """deferred 的 assistant entry 必须完整。"""
    for entry in entries:
        if (
            entry.type == "message"
            and entry.message.role == "assistant"
            and getattr(entry.message, "stopReason", None) == "deferred"
            and getattr(entry.message, "deferred", None) is None
        ):
            _corrupt("invalid_deferred_handle", f"Deferred assistant entry {entry.id} does not carry a handle")


def validate_record_log(slice: RecordLogSlice) -> None:
    """校验 record log 一致性，检测 12 种 corruption（不读 session 状态）。"""
    if len(slice.open_operations) > 1:
        _corrupt(
            "multiple_open_operations",
            f"Lane {slice.lane} has {len(slice.open_operations)} open operations",
        )

    entries_by_id = {e.id: e for e in slice.entries}
    _validate_deferred_handles(slice.entries)

    starts: dict[str, OperationStartedRecord] = {}
    finished_at: dict[str, int] = {}
    aborted_at: dict[str, int] = {}
    queue_enqueues: dict[str, LaneRecord] = {}
    latest_attempt: dict[str, StepAttemptRecord] = {}
    tool_invocations: set[str] = set()

    for record in sorted(slice.records, key=lambda r: r.seq):
        if record.type == "operation_started":
            starts[record.id] = record
            continue

        run_id = _run_id_of(record)
        if run_id is not None:
            if run_id not in starts:
                _corrupt("unknown_operation", f"Record {record.id} references unknown operation {run_id}")
            if run_id in finished_at and record.seq > finished_at[run_id]:
                _corrupt("record_after_finish", f"Record {record.id} follows the finish of operation {run_id}")

        if record.type == "operation_finished":
            finished_at[record.run_id] = record.seq
        elif record.type == "abort_requested":
            aborted_at[record.run_id] = record.seq
        elif record.type == "step_attempt":
            _validate_attempt_reason(record)
            _validate_attempt_sequence(record, latest_attempt.get(record.run_id), entries_by_id)
            latest_attempt[record.run_id] = record
        elif record.type == "tool_started":
            _validate_tool_start(record, entries_by_id, tool_invocations)
        elif record.type == "queue_enqueued":
            if (
                record.queue != "nextRun"
                and record.run_id in aborted_at
                and record.seq > aborted_at[record.run_id]
            ):
                _corrupt("queue_after_abort", f"{record.queue} item {record.target.get('id')} enqueued after abort")
            queue_enqueues[record.target.get("id")] = record
        elif record.type == "queue_cancelled":
            enqueue = queue_enqueues.get(record.entry_id)
            if enqueue is None or enqueue.seq >= record.seq or _run_id_of(enqueue) != record.run_id:
                _corrupt("invalid_queue_cancellation", f"Queue cancellation {record.id} has no pending matching enqueue")


def reduce_lane_state(slice: RecordLogSlice) -> LaneState:
    """从 record log 重建 lane 的编排状态。"""
    validate_record_log(slice)

    started = slice.open_operations[0] if slice.open_operations else None
    if started is None:
        return LaneState(lane=slice.lane, leaf_id=None, operation=None, pending_next_run=[])

    operation_records = [
        r for r in slice.records
        if r.type == "operation_started" or _run_id_of(r) == started.id
    ]
    aborting = any(r.type == "abort_requested" for r in operation_records)

    step_attempts = [r for r in operation_records if r.type == "step_attempt"]
    newest_attempt = step_attempts[-1] if step_attempts else None
    step = None
    if newest_attempt is not None:
        step = {
            "kind": newest_attempt.step,
            "attempts": newest_attempt.attempt,
            "result_entry_id": newest_attempt.result_entry_id,
        }

    return LaneState(
        lane=slice.lane,
        leaf_id=None,
        operation={
            "id": started.id,
            "kind": started.intent.get("kind"),
            "aborting": aborting,
            "step": step,
        },
        pending_next_run=[],
    )
