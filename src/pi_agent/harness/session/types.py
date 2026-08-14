"""会话数据模型（对应 pi 的 harness/session/types.ts）。

Entry = 会话树节点（消息、配置变更、压缩摘要…）
Record = 操作日志（operation/tool/queue…），用于崩溃后恢复状态（reducer 用）
"""
from dataclasses import dataclass
from typing import Any, Literal

from pi_agent.types import Message


# ============ Entry（会话树节点）============

@dataclass
class MessageEntry:
    message: Message
    id: str = ""
    seq: int = 0
    parent_id: str | None = None
    timestamp: int = 0
    type: Literal["message"] = "message"


@dataclass
class ModelChangeEntry:
    provider: str
    model_id: str
    id: str = ""
    seq: int = 0
    parent_id: str | None = None
    timestamp: int = 0
    type: Literal["model_change"] = "model_change"


@dataclass
class ThinkingLevelEntry:
    thinking_level: str
    id: str = ""
    seq: int = 0
    parent_id: str | None = None
    timestamp: int = 0
    type: Literal["thinking_level_change"] = "thinking_level_change"


@dataclass
class ActiveToolsEntry:
    active_tool_names: list[str]
    id: str = ""
    seq: int = 0
    parent_id: str | None = None
    timestamp: int = 0
    type: Literal["active_tools_change"] = "active_tools_change"


@dataclass
class CompactionEntry:
    summary: str
    retained_tail: list[Message]
    tokens_before: int
    details: Any = None
    id: str = ""
    seq: int = 0
    parent_id: str | None = None
    timestamp: int = 0
    type: Literal["compaction"] = "compaction"


@dataclass
class BranchSummaryEntry:
    from_id: str
    summary: str
    details: Any = None
    id: str = ""
    seq: int = 0
    parent_id: str | None = None
    timestamp: int = 0
    type: Literal["branch_summary"] = "branch_summary"


@dataclass
class CustomEntry:
    custom_type: str
    data: Any = None
    id: str = ""
    seq: int = 0
    parent_id: str | None = None
    timestamp: int = 0
    type: Literal["custom"] = "custom"


Entry = (
    MessageEntry
    | ModelChangeEntry
    | ThinkingLevelEntry
    | ActiveToolsEntry
    | CompactionEntry
    | BranchSummaryEntry
    | CustomEntry
)


# ============ Record（操作日志，用于恢复）============

@dataclass
class OperationStartedRecord:
    id: str
    seq: int
    lane: str
    timestamp: int
    source_leaf_id: str | None
    intent: dict  # {kind: "run"|"compaction"|"navigation", ...}
    type: Literal["operation_started"] = "operation_started"


@dataclass
class AbortRequestedRecord:
    id: str
    seq: int
    lane: str
    timestamp: int
    run_id: str
    type: Literal["abort_requested"] = "abort_requested"


@dataclass
class OperationFinishedRecord:
    id: str
    seq: int
    lane: str
    timestamp: int
    run_id: str
    outcome: str  # completed | aborted | failed | declined
    error: dict | None = None
    type: Literal["operation_finished"] = "operation_finished"


@dataclass
class StepAttemptRecord:
    id: str
    seq: int
    lane: str
    timestamp: int
    run_id: str
    step: str  # assistant | branch_summary | compaction
    attempt: int
    result_entry_id: str
    compaction_reason: str | None = None
    type: Literal["step_attempt"] = "step_attempt"


@dataclass
class ToolStartedRecord:
    id: str
    seq: int
    lane: str
    timestamp: int
    run_id: str
    assistant_entry_id: str
    tool_index: int
    tool_call_id: str
    tool_name: str
    effective_args: dict
    result_entry_id: str
    replay: str  # never | safe
    type: Literal["tool_started"] = "tool_started"


@dataclass
class QueueEnqueuedRecord:
    id: str
    seq: int
    lane: str
    timestamp: int
    queue: str  # steer | followUp | nextRun
    target: dict
    run_id: str | None = None
    type: Literal["queue_enqueued"] = "queue_enqueued"


@dataclass
class QueueCancelledRecord:
    id: str
    seq: int
    lane: str
    timestamp: int
    entry_id: str
    run_id: str | None = None
    type: Literal["queue_cancelled"] = "queue_cancelled"


@dataclass
class WriteDeferredRecord:
    id: str
    seq: int
    lane: str
    timestamp: int
    run_id: str
    target: dict
    type: Literal["write_deferred"] = "write_deferred"


@dataclass
class UsageRecord:
    id: str
    seq: int
    lane: str
    timestamp: int
    usage: dict
    cause: str
    run_id: str | None = None
    entry_id: str | None = None
    type: Literal["usage"] = "usage"


LaneRecord = (
    OperationStartedRecord
    | AbortRequestedRecord
    | OperationFinishedRecord
    | StepAttemptRecord
    | ToolStartedRecord
    | QueueEnqueuedRecord
    | QueueCancelledRecord
    | WriteDeferredRecord
    | UsageRecord
)


# ============ 元数据 ============

@dataclass
class SessionMetadata:
    id: str
    created_at: int
    parent_session_id: str | None = None


@dataclass
class SessionStats:
    message_count: int = 0
    total_tokens: int = 0
    cost_total: float = 0.0
