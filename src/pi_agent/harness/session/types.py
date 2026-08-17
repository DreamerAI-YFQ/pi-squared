"""
会话数据模型（对应 pi 的 harness/session/types.ts）。

这个文件定义了 Agent 对话的"记忆格式"，是整个会话持久化的核心。

核心设计：Entry/Record 双轨制
- Entry（会话树节点）：存储用户/Agent 的对话内容、配置变更、压缩摘要等
  → 用于恢复对话上下文，让 Agent 知道之前发生了什么
- Record（操作日志）：存储操作过程（开始/结束/工具调用/队列操作等）
  → 用于崩溃恢复，让系统知道恢复到什么状态

为什么分开存？
- Entry 关注"内容"（对话历史）
- Record 关注"过程"（状态重建）
- 分开后可以独立使用：Entry 用于上下文压缩，Record 用于崩溃恢复

类比游戏系统：
- Entry = 游戏存档（你在哪、有什么装备）
- Record = 操作日志（你按了什么键、做了什么动作）

============ 核心设计 ============
这个文件就是：

定义了 7 种 Entry（存对话内容）
定义了 9 种 Record（存操作过程）
定义了会话元数据（会话ID、创建时间、统计信息）
是整个会话持久化的基础数据结构。

"""
from dataclasses import dataclass
from typing import Any, Literal

from pi_agent.types import Message


# ============ Entry（会话树节点）============
# Entry 构成了对话的树形结构，每个节点都有自己的 ID、序列号、父节点 ID


@dataclass
class MessageEntry:
    """消息节点：存储用户或 Agent 的消息。

    这是最基础的 Entry 类型，用于记录对话内容。
    """
    message: Message  # 消息内容（User/Assistant/ToolResult）
    id: str = ""  # 节点唯一标识
    seq: int = 0  # 序列号（用于确保顺序）
    parent_id: str | None = None  # 父节点 ID（构建树形结构）
    timestamp: int = 0  # 时间戳
    type: Literal["message"] = "message"  # 类型标记


@dataclass
class ModelChangeEntry:
    """模型配置变更节点：记录切换了哪个模型。

    用于追踪对话过程中模型的切换历史。
    """
    provider: str  # 提供商（如 "openai"、"anthropic"）
    model_id: str  # 模型 ID（如 "gpt-4"、"claude-3-opus"）
    id: str = ""  # 节点唯一标识
    seq: int = 0  # 序列号
    parent_id: str | None = None  # 父节点 ID
    timestamp: int = 0  # 时间戳
    type: Literal["model_change"] = "model_change"  # 类型标记


@dataclass
class ThinkingLevelEntry:
    """思考级别变更节点：记录 Agent 的思考深度设置。

    用于控制 Agent 的推理深度。
    """
    thinking_level: str  # 思考级别（如 "minimal"、"standard"、"deep"）
    id: str = ""  # 节点唯一标识
    seq: int = 0  # 序列号
    parent_id: str | None = None  # 父节点 ID
    timestamp: int = 0  # 时间戳
    type: Literal["thinking_level_change"] = "thinking_level_change"  # 类型标记


@dataclass
class ActiveToolsEntry:
    """活跃工具变更节点：记录当前启用了哪些工具。

    用于追踪对话过程中工具集的变化。
    """
    active_tool_names: list[str]  # 启用的工具名称列表
    id: str = ""  # 节点唯一标识
    seq: int = 0  # 序列号
    parent_id: str | None = None  # 父节点 ID
    timestamp: int = 0  # 时间戳
    type: Literal["active_tools_change"] = "active_tools_change"  # 类型标记


@dataclass
class CompactionEntry:
    """压缩节点：记录对话历史的压缩摘要。

    当对话太长时，会压缩早期的对话为摘要，节省 token。
    """
    summary: str  # 压缩后的摘要文本
    retained_tail: list[Message]  # 保留的尾部消息（不压缩的部分）
    tokens_before: int  # 压缩前的 token 数
    details: Any = None  # 其他详细信息
    id: str = ""  # 节点唯一标识
    seq: int = 0  # 序列号
    parent_id: str | None = None  # 父节点 ID
    timestamp: int = 0  # 时间戳
    type: Literal["compaction"] = "compaction"  # 类型标记


@dataclass
class BranchSummaryEntry:
    """分支摘要节点：记录分支路径的摘要。

    当对话分叉时（比如尝试不同的方案），记录每个分支的摘要。
    """
    from_id: str  # 分支的起始节点 ID
    summary: str  # 分支摘要
    details: Any = None  # 其他详细信息
    id: str = ""  # 节点唯一标识
    seq: int = 0  # 序列号
    parent_id: str | None = None  # 父节点 ID
    timestamp: int = 0  # 时间戳
    type: Literal["branch_summary"] = "branch_summary"  # 类型标记


@dataclass
class CustomEntry:
    """自定义节点：扩展用，允许存储任意类型的数据。

    为未来扩展预留，可以存储自定义的数据结构。
    """
    custom_type: str  # 自定义类型标识
    data: Any = None  # 自定义数据
    id: str = ""  # 节点唯一标识
    seq: int = 0  # 序列号
    parent_id: str | None = None  # 父节点 ID
    timestamp: int = 0  # 时间戳
    type: Literal["custom"] = "custom"  # 类型标记


# Entry 联合类型：可以是上述 7 种 Entry 中的任意一种
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
# Record 记录操作过程的每个步骤，用于崩溃后重建状态


@dataclass
class OperationStartedRecord:
    """操作开始记录：记录一个操作的启动。

    这是 Record 的起点，对应一次完整的对话循环或操作。
    """
    id: str  # 记录唯一标识
    seq: int  # 序列号（必须连续）
    lane: str  # 轨道标识（用于并发控制）
    timestamp: int  # 时间戳
    source_leaf_id: str | None  # 起始节点 ID
    intent: dict  # 操作意图（{kind: "run"|"compaction"|"navigation", ...}）
    type: Literal["operation_started"] = "operation_started"  # 类型标记


@dataclass
class AbortRequestedRecord:
    """中止请求记录：记录用户请求中止操作。

    当用户点击"停止"按钮时，生成此记录。
    """
    id: str  # 记录唯一标识
    seq: int  # 序列号
    lane: str  # 轨道标识
    timestamp: int  # 时间戳
    run_id: str  # 要中止的操作 ID
    type: Literal["abort_requested"] = "abort_requested"  # 类型标记


@dataclass
class OperationFinishedRecord:
    """操作完成记录：记录操作的最终状态。

    这是 Record 的终点，标记操作完成、中止、失败或拒绝。
    """
    id: str  # 记录唯一标识
    seq: int  # 序列号
    lane: str  # 轨道标识
    timestamp: int  # 时间戳
    run_id: str  # 操作 ID
    outcome: str  # 操作结果（completed | aborted | failed | declined）
    error: dict | None = None  # 错误信息（如果失败）
    type: Literal["operation_finished"] = "operation_finished"  # 类型标记


@dataclass
class StepAttemptRecord:
    """步骤尝试记录：记录操作中的每个步骤。

    一个操作可能包含多个步骤（如 assistant 调用、分支摘要、压缩等）。
    """
    id: str  # 记录唯一标识
    seq: int  # 序列号
    lane: str  # 轨道标识
    timestamp: int  # 时间戳
    run_id: str  # 操作 ID
    step: str  # 步骤类型（assistant | branch_summary | compaction）
    attempt: int  # 尝试次数（重试时会递增）
    result_entry_id: str  # 结果对应的 Entry ID
    compaction_reason: str | None = None  # 压缩原因（如果是压缩步骤）
    type: Literal["step_attempt"] = "step_attempt"  # 类型标记


@dataclass
class ToolStartedRecord:
    """工具开始记录：记录工具调用的开始。

    用于追踪 Agent 调用了哪些工具。
    """
    id: str  # 记录唯一标识
    seq: int  # 序列号
    lane: str  # 轨道标识
    timestamp: int  # 时间戳
    run_id: str  # 操作 ID
    assistant_entry_id: str  # 触发工具调用的 assistant 消息 ID
    tool_index: int  # 工具索引（一条消息可能调用多个工具）
    tool_call_id: str  # 工具调用 ID
    tool_name: str  # 工具名称（如 "read"、"write"）
    effective_args: dict  # 实际传递给工具的参数
    result_entry_id: str  # 工具结果对应的 Entry ID
    replay: str  # 重放策略（never | safe）
    type: Literal["tool_started"] = "tool_started"  # 类型标记


@dataclass
class QueueEnqueuedRecord:
    """队列入队记录：记录任务加入队列。

    用于追踪待处理的任务队列。
    """
    id: str  # 记录唯一标识
    seq: int  # 序列号
    lane: str  # 轨道标识
    timestamp: int  # 时间戳
    queue: str  # 队列名称（steer | followUp | nextRun）
    target: dict  # 队列目标（任务描述）
    run_id: str | None = None  # 关联的操作 ID
    type: Literal["queue_enqueued"] = "queue_enqueued"  # 类型标记


@dataclass
class QueueCancelledRecord:
    """队列取消记录：记录队列任务的取消。

    当队列中的任务被取消时，生成此记录。
    """
    id: str  # 记录唯一标识
    seq: int  # 序列号
    lane: str  # 轨道标识
    timestamp: int  # 时间戳
    entry_id: str  # 被取消的任务 ID
    run_id: str | None = None  # 关联的操作 ID
    type: Literal["queue_cancelled"] = "queue_cancelled"  # 类型标记


@dataclass
class WriteDeferredRecord:
    """延迟写入记录：记录延迟写入的操作。

    某些操作需要延迟写入（如需要在其他操作完成后才能写入）。
    """
    id: str  # 记录唯一标识
    seq: int  # 序列号
    lane: str  # 轨道标识
    timestamp: int  # 时间戳
    run_id: str  # 操作 ID
    target: dict  # 延迟写入的目标
    type: Literal["write_deferred"] = "write_deferred"  # 类型标记


@dataclass
class UsageRecord:
    """使用量记录：记录 token 使用量和成本。

    用于追踪 API 调用的资源消耗。
    """
    id: str  # 记录唯一标识
    seq: int  # 序列号
    lane: str  # 轨道标识
    timestamp: int  # 时间戳
    usage: dict  # 使用量详情（{prompt_tokens, completion_tokens, total_tokens}）
    cause: str  # 使用原因（如 "assistant_call"、"tool_call"）
    run_id: str | None = None  # 关联的操作 ID
    entry_id: str | None = None  # 关联的 Entry ID
    type: Literal["usage"] = "usage"  # 类型标记


# LaneRecord 联合类型：可以是上述 9 种 Record 中的任意一种
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
# 会话级别的元数据，用于管理会话本身


@dataclass
class SessionMetadata:
    """会话元数据：记录会话的基本信息。

    用于会话的创建和追踪。
    """
    id: str  # 会话唯一标识
    created_at: int  # 创建时间戳
    parent_session_id: str | None = None  # 父会话 ID（用于会话分叉）


@dataclass
class SessionStats:
    """会话统计：记录会话的使用统计。

    用于追踪会话的资源消耗。
    """
    message_count: int = 0  # 消息总数
    total_tokens: int = 0  # 总 token 数
    cost_total: float = 0.0  # 总成本
