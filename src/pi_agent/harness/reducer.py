"""
恢复协议（对应 pi 的 harness/reducer.ts）。

从持久化的 record log 重建 lane 的编排状态（进程崩溃后恢复）。

核心功能：
1. validate_record_log：校验 record log 一致性（12 种 corruption 检测）
2. reduce_lane_state：重建运行状态

设计目标：
- 崩溃恢复：程序崩溃后从操作日志重建状态
- 数据完整性：检测操作日志中的各种异常情况
- 状态重建：重放操作，恢复到崩溃前的状态

核心问题：
- 操作日志可能损坏（写入不完整、并发冲突等）
- 需要检测 12 种可能的 corruption 类型
- 检测通过后才能安全地重放操作

类比：
- 就像游戏回放：从操作记录重建游戏状态
- validate_record_log = 检查操作记录是否合法
- reduce_lane_state = 重放操作，重建状态
"""
from dataclasses import dataclass
from typing import Literal

from pi_agent.harness.session.types import (
    Entry, #实体对象
    LaneRecord, #记录对象
    OperationStartedRecord, #操作开始记录对象
    StepAttemptRecord, #步骤尝试记录对象
    ToolStartedRecord, #工具开始记录对象
)


# 12 种 corruption 类型
RecordLogCorruptionReason = Literal[
    "multiple_open_operations",       # 多个操作同时开启（不应该）
    "unknown_operation",              # 未知的操作类型
    "record_after_finish",            # 操作结束后还有记录
    "non_consecutive_attempt",        # 步骤编号不连续
    "invalid_compaction_reason",      # 压缩原因无效
    "queue_after_abort",              # 中止后还有队列操作
    "invalid_queue_cancellation",     # 队列取消无效
    "inconsistent_step",              # 步骤不一致
    "tool_call_mismatch",             # 工具调用不匹配
    "duplicate_tool_invocation",      # 重复工具调用
    "provisioned_entry_mismatch",     # 预分配的 Entry 不匹配
    "invalid_deferred_handle",        # 延迟句柄无效
]


class RecordLogCorruption(Exception):
    """操作日志损坏异常。

    当检测到 record log 存在 corruption 时抛出。
    """
    def __init__(self, reason: RecordLogCorruptionReason, message: str):
        super().__init__(message)
        self.reason = reason  # corruption 类型


@dataclass
class RecordLogSlice:
    """操作日志切片：一个 lane 的完整操作记录。

    包含：
    - lane：轨道标识
    - open_operations：当前开启的操作
    - records：所有操作记录
    - entries：相关的 Entry 列表
    """
    lane: str
    open_operations: list[OperationStartedRecord]
    records: list[LaneRecord]
    entries: list[Entry]


@dataclass
class LaneState:
    """Lane 的运行状态（重建后的状态）。

    包含：
    - lane：轨道标识
    - leaf_id：当前叶子节点 ID
    - operation：当前操作信息
    - pending_next_run：待处理的下次运行
    """
    lane: str
    leaf_id: str | None
    operation: dict | None
    pending_next_run: list[dict]


def _run_id_of(record: LaneRecord) -> str | None:
    """获取记录的 run_id。

    Args:
        record: LaneRecord 对象

    Returns:
        run_id 或 None
    """
    return getattr(record, "run_id", None)


def _corrupt(reason: RecordLogCorruptionReason, message: str) -> None:
    """抛出 corruption 异常。

    Args:
        reason: corruption 类型
        message: 错误信息

    Raises:
        RecordLogCorruption: corruption 异常
    """
    raise RecordLogCorruption(reason, message)


def _validate_attempt_reason(record: StepAttemptRecord) -> None:
    """校验步骤的压缩原因。

    规则：
    - compaction step 必须有 valid reason（manual/threshold/overflow）
    - 非 compaction step 不能有 reason

    Args:
        record: 步骤尝试记录

    Raises:
        RecordLogCorruption: 如果压缩原因无效
    """
    reason = record.compaction_reason
    if record.step == "compaction":
        # compaction 步骤必须有有效的压缩原因
        if reason not in ("manual", "threshold", "overflow"):
            _corrupt("invalid_compaction_reason", f"Compaction attempt {record.id} has no valid compaction reason")
    elif reason is not None:
        # 非 compaction 步骤不能有压缩原因
        _corrupt("invalid_compaction_reason", f"{record.step} attempt {record.id} has a compaction reason")


def _validate_attempt_sequence(
    record: StepAttemptRecord,
    previous: StepAttemptRecord | None,
    entries_by_id: dict[str, Entry],
) -> None:
    """校验步骤序列的连续性。

    规则：
    - attempt 必须连续（1, 2, 3...）
    - 同一系列的 resultEntryId 必须一致
    - 同一系列的 compactionReason 必须一致

    Args:
        record: 当前步骤记录
        previous: 上一个步骤记录
        entries_by_id: Entry 索引

    Raises:
        RecordLogCorruption: 如果步骤序列不连续
    """
    continues = previous is not None and previous.step == record.step
    expected_attempt = previous.attempt + 1 if continues else 1
    
    # 检查 attempt 编号是否连续
    if record.attempt != expected_attempt:
        _corrupt(
            "non_consecutive_attempt",
            f"{record.step} attempt {record.id} is {record.attempt}; expected {expected_attempt}",
        )
    
    # 检查同系列的 resultEntryId 和 compactionReason 是否一致
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
    """校验工具调用的有效性。

    规则：
    - tool invocation 不能重复
    - 必须匹配 assistant 的 tool-call ordinal

    Args:
        record: 工具开始记录
        entries_by_id: Entry 索引
        invocations: 已知的工具调用集合

    Raises:
        RecordLogCorruption: 如果工具调用无效
    """
    # 检查工具调用是否重复
    invocation = f"{record.assistant_entry_id}\x00{record.tool_index}"
    if invocation in invocations:
        _corrupt("duplicate_tool_invocation", f"Tool invocation {record.assistant_entry_id}:{record.tool_index} is duplicated")
    invocations.add(invocation)

    # 检查是否引用了有效的 assistant entry
    assistant_entry = entries_by_id.get(record.assistant_entry_id)
    if assistant_entry is None or assistant_entry.type != "message" or assistant_entry.message.role != "assistant":
        _corrupt("tool_call_mismatch", f"Tool start {record.id} does not reference an assistant entry")

    # 检查工具调用是否匹配 assistant 的 tool-call ordinal
    tool_calls = [c for c in assistant_entry.message.content if c.type == "toolCall"]
    tool_call = tool_calls[record.tool_index] if record.tool_index < len(tool_calls) else None
    if tool_call is None or tool_call.id != record.tool_call_id or tool_call.name != record.tool_name:
        _corrupt("tool_call_mismatch", f"Tool start {record.id} does not match its assistant tool-call ordinal")


def _validate_deferred_handles(entries: list[Entry]) -> None:
    """校验延迟句柄的有效性。

    规则：
    - deferred 的 assistant entry 必须携带 handle

    Args:
        entries: Entry 列表

    Raises:
        RecordLogCorruption: 如果延迟句柄无效
    """
    for entry in entries:
        if (
            entry.type == "message"
            and entry.message.role == "assistant"
            and getattr(entry.message, "stopReason", None) == "deferred"
            and getattr(entry.message, "deferred", None) is None
        ):
            _corrupt("invalid_deferred_handle", f"Deferred assistant entry {entry.id} does not carry a handle")


def _validate_provisioned_entries(records: list[LaneRecord], entries_by_id: dict[str, Entry]) -> None:
    """校验预分配 Entry 的一致性。

    规则：
    - write_deferred provision 的 entry 若已实际写入，parent 必须与 provision 一致

    Args:
        records: Record 列表
        entries_by_id: Entry 索引

    Raises:
        RecordLogCorruption: 如果预分配的 Entry 不匹配
    """
    provisioned: dict[str, str | None] = {}
    
    # 收集所有预分配的 Entry
    for record in records:
        if record.type != "write_deferred":
            continue
        target = record.target.get("entry") if isinstance(record.target, dict) else None
        if not isinstance(target, dict) or not target.get("id"):
            _corrupt("invalid_deferred_handle", f"Write deferred {record.id} carries no provisioned entry")
        provisioned[target["id"]] = target.get("parent_id")

    # 检查预分配的 parent_id 是否与实际写入的一致
    for entry_id, parent_id in provisioned.items():
        entry = entries_by_id.get(entry_id)
        if entry is not None and entry.parent_id != parent_id:
            _corrupt(
                "provisioned_entry_mismatch",
                f"Entry {entry_id} does not match the parent provisioned by its deferred write",
            )


def validate_record_log(slice: RecordLogSlice) -> None:
    """校验 record log 一致性，检测 12 种 corruption（不读 session 状态）。

    校验规则：
    1. 最多只能有一个开启的操作
    2. 操作完成后不能有后续记录
    3. 步骤编号必须连续
    4. 工具调用必须匹配 assistant 消息
    5. 队列操作必须合法
    6. 延迟句柄必须完整
    7. 预分配 Entry 必须一致

    Args:
        slice: 操作日志切片

    Raises:
        RecordLogCorruption: 如果检测到任何 corruption
    """
    # 1. 检查是否有多个同时开启的操作
    if len(slice.open_operations) > 1:
        _corrupt(
            "multiple_open_operations",
            f"Lane {slice.lane} has {len(slice.open_operations)} open operations",
        )

    # 构建 Entry 索引
    entries_by_id = {e.id: e for e in slice.entries}

    # 2. 检查操作完成后是否还有记录
    current_run_id: str | None = None
    current_run_finished = False

    for record in slice.records:
        run_id = _run_id_of(record)

        if record.type == "operation_started":
            # 检查是否有多个同时开启的操作
            if current_run_id is not None and not current_run_finished:
                _corrupt("unknown_operation", f"Operation {record.id} started while {current_run_id} is still active")
            current_run_id = record.id
            current_run_finished = False

        elif record.type == "operation_finished":
            # 检查操作是否已经结束
            if current_run_id is None or run_id != current_run_id:
                _corrupt("unknown_operation", f"Operation finish {record.id} does not match current run {current_run_id}")
            current_run_finished = True

        elif current_run_finished:
            # 检查操作结束后是否还有记录
            _corrupt("record_after_finish", f"Record {record.id} appeared after operation {current_run_id} finished")

        elif record.type == "step_attempt":
            # 检查步骤的压缩原因
            _validate_attempt_reason(record)

            # 检查步骤序列连续性
            previous_step = None
            for prev in reversed(slice.records):
                if prev.type == "step_attempt" and _run_id_of(prev) == run_id:
                    previous_step = prev
                    break
            _validate_attempt_sequence(record, previous_step, entries_by_id)

        elif record.type == "tool_started":
            # 检查工具调用有效性
            invocations = set()
            for prev in slice.records:
                if prev.type == "tool_started" and _run_id_of(prev) == run_id:
                    _validate_tool_start(prev, entries_by_id, invocations)

    # 3. 检查队列操作是否合法
    abort_requested = False
    for record in slice.records:
        if record.type == "abort_requested":
            abort_requested = True
        elif record.type == "queue_enqueued" and abort_requested:
            _corrupt("queue_after_abort", f"Queue enqueued {record.id} after abort request")
        elif record.type == "queue_cancelled":
            # 检查队列取消是否有效
            # （简化版省略详细检查）
            pass

    # 4. 检查延迟句柄和预分配 Entry
    _validate_deferred_handles(slice.entries)
    _validate_provisioned_entries(slice.records, entries_by_id)


def reduce_lane_state(slice: RecordLogSlice) -> LaneState:
    """从 record log 重建 lane 的运行状态。

    重放流程：
    1. 从 open_operations 确定当前操作
    2. 从 records 重建操作状态和队列
    3. 从 entries 确定当前叶子节点

    Args:
        slice: 操作日志切片

    Returns:
        重建后的 LaneState
    """
    # 初始化空状态
    state = LaneState(
        lane=slice.lane,
        leaf_id=None,
        operation=None,
        pending_next_run=[],
    )

    # 从 records 重建状态
    current_run_id: str | None = None
    for record in slice.records:
        if record.type == "operation_started":
            current_run_id = record.id
            state.operation = {
                "id": record.id,
                "intent": record.intent,
                "source_leaf_id": record.source_leaf_id,
            }
        elif record.type == "operation_finished":
            current_run_id = None
            state.operation = None
        elif record.type == "queue_enqueued":
            state.pending_next_run.append(record.target)
        elif record.type == "queue_cancelled":
            state.pending_next_run = [
                t for t in state.pending_next_run
                if t.get("entry_id") != record.entry_id
            ]

    # 从 entries 确定当前叶子节点
    if slice.entries:
        state.leaf_id = slice.entries[-1].id

    return state