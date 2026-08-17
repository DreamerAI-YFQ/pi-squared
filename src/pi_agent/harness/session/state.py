"""
会话状态机（对应 pi 的 harness/session/state.ts）。

核心：维护会话状态（entries/records/lanes/log/stats），校验并应用 mutation。

设计目标：
1. 确保数据一致性：seq 必须连续，不能跳号
2. 支持崩溃恢复：从 Record 日志重建状态
3. 提供查询接口：支持各种查询需求

核心概念：
- SessionMutation：变更操作的单位（5 种类型）
- SessionState：状态机，维护所有状态并应用 mutation
- seq 连续性：这是崩溃恢复的地基，seq 必须连续（seq != self._sequence + 1 即拒）

类比：
- Mutation = 游戏操作（移动、攻击、使用道具）
- SessionState = 游戏状态管理器（记录所有操作、校验合法性、更新状态）
- seq 连续性 = 时间线（操作必须按顺序执行，不能跳过）
"""
from dataclasses import dataclass
from typing import Literal, Union

from pi_agent.harness.session.types import (
    Entry,
    LaneRecord,
    OperationStartedRecord,
    SessionStats,
)


class SessionError(Exception):
    """会话错误：表示会话状态机的校验失败。

    当 mutation 不符合规则时抛出（如 seq 不连续、ID 重复等）。
    """
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code  # 错误码（如 "invalid_entry"、"already_exists"）


# ============ Mutation 定义 ============
# Mutation 是"追加日志"的单位，每次状态变更都是一个 Mutation


@dataclass
class EntryMutation:
    """Entry 变更：添加一个 Entry 到会话树。

    用于记录用户消息、Agent 回复、配置变更等。
    """
    entry: Entry  # 要添加的 Entry
    lane: str | None = None  # 轨道标识（可选，用于并发控制）
    kind: Literal["entry"] = "entry"  # 类型标记


@dataclass
class RecordMutation:
    """Record 变更：添加一个 Record 到操作日志。

    用于记录操作过程（开始、结束、工具调用等）。
    """
    record: LaneRecord  # 要添加的 Record
    kind: Literal["record"] = "record"  # 类型标记


@dataclass
class LaneMutation:
    """Lane 变更：更新轨道的叶子节点。

    Lane 用于并发控制，每个 Lane 有自己的叶子节点。
    """
    seq: int  # 序列号
    lane: str  # 轨道标识
    leaf_id: str | None  # 叶子节点 ID（轨道的最新节点）
    kind: Literal["lane"] = "lane"  # 类型标记


@dataclass
class NameFactMutation:
    """名称事实变更：更新会话名称。

    用于给会话起名或改名。
    """
    seq: int  # 序列号
    name: str | None  # 会话名称（None 表示删除名称）
    kind: Literal["fact_name"] = "fact_name"  # 类型标记


@dataclass
class LabelFactMutation:
    """标签事实变更：为 Entry 添加或删除标签。

    用于标记重要的 Entry（如用户标注）。
    """
    seq: int  # 序列号
    target_id: str  # 目标 Entry 的 ID
    label: str | None  # 标签内容（None 表示删除标签）
    kind: Literal["fact_label"] = "fact_label"  # 类型标记


# SessionMutation 联合类型：可以是上述 5 种 Mutation 中的任意一种
SessionMutation = Union[
    EntryMutation, RecordMutation, LaneMutation, NameFactMutation, LabelFactMutation
]


class SessionState:
    """会话状态机：维护会话的所有状态。

    核心职责：
    1. 维护 entries、records、lanes、log、stats 等状态
    2. 校验 mutation 的合法性（seq 连续性、ID 唯一性等）
    3. 应用 mutation 更新状态
    4. 提供查询接口

    重放恢复的核心：通过重放 Record 日重建状态。
    """

    def __init__(self):
        """初始化空会话状态。"""
        self._sequence = 0  # 当前序列号（必须连续递增）
        self._used_ids: set[str] = set()  # 已使用的 ID 集合（确保唯一性）
        self._entries: list[Entry] = []  # Entry 列表（按顺序）
        self._entries_by_id: dict[str, Entry] = {}  # Entry 索引（按 ID 查找）
        self._records: list[LaneRecord] = []  # Record 列表（按顺序）
        self._open_operations: dict[str, dict[str, OperationStartedRecord]] = {}  # 进行中的操作（按 lane 分组）
        self._lanes: dict[str, str | None] = {"main": None}  # 轨道状态（lane → leaf_id）
        self._log: list[dict] = []  # 操作日志（用于重放）
        self._stats = SessionStats()  # 会话统计（消息数、token 数、成本）
        self._name: str | None = None  # 会话名称
        self._labels: dict[str, str] = {}  # Entry 标签（entry_id → label）

    # ============ mutation 应用 ============

    def apply_mutation(self, mutation: SessionMutation) -> None:
        """应用一个 mutation 到状态机。

        这是状态机的核心入口，所有状态变更都通过这个方法。

        Args:
            mutation: 要应用的 mutation

        Raises:
            SessionError: 如果 mutation 不合法（seq 不连续、ID 重复等）
        """
        # 提取序列号
        if mutation.kind == "entry":
            seq = mutation.entry.seq
        elif mutation.kind == "record":
            seq = mutation.record.seq
        else:
            seq = mutation.seq

        # 核心校验：seq 必须连续（seq != self._sequence + 1 即拒）
        # 这是崩溃恢复的地基，确保操作按顺序执行
        if seq != self._sequence + 1:
            raise SessionError("invalid_entry", f"non-consecutive seq {seq}")

        # 根据类型分发到具体的处理方法
        if mutation.kind == "entry":
            self._apply_entry(mutation)
        elif mutation.kind == "record":
            self._apply_record(mutation)
        elif mutation.kind == "lane":
            self._apply_lane(mutation)
        elif mutation.kind == "fact_name":
            self._apply_name(mutation)
        else:
            self._apply_label(mutation)

    def _apply_entry(self, mutation: EntryMutation) -> None:
        """应用 Entry 变更。

        校验规则：
        1. ID 不能重复
        2. 如果指定了 lane，Entry 必须链接到 lane 的叶子节点
        3. parent_id 必须存在（如果是非根节点）

        Args:
            mutation: Entry 变更

        Raises:
            SessionError: 如果校验失败
        """
        entry = mutation.entry

        # 校验 1：ID 不能重复
        if entry.id in self._used_ids:
            raise SessionError("already_exists", f"duplicate id {entry.id}")

        # 校验 2：如果指定了 lane，Entry 必须链接到 lane 的叶子节点
        if mutation.lane is not None:
            leaf_id = self._lanes.get(mutation.lane)
            if leaf_id is None and mutation.lane not in self._lanes:
                raise SessionError("invalid_lane", f"missing lane {mutation.lane}")
            if entry.parent_id != leaf_id:
                raise SessionError("invalid_entry", "entry does not chain to the lane leaf")

        # 校验 3：parent_id 必须存在
        if entry.parent_id is not None and entry.parent_id not in self._entries_by_id:
            raise SessionError("invalid_entry", f"missing parent {entry.parent_id}")

        # 应用变更
        self._sequence = entry.seq  # 更新序列号
        self._used_ids.add(entry.id)  # 记录已使用的 ID
        self._entries.append(entry)  # 添加到 Entry 列表
        self._entries_by_id[entry.id] = entry  # 添加到索引
        if mutation.lane is not None:
            self._lanes[mutation.lane] = entry.id  # 更新 lane 的叶子节点
        self._log.append({"kind": "entry", "seq": entry.seq, "entry": entry})  # 记录日志
        if entry.type == "message":
            self._stats.message_count += 1  # 更新统计

    def _apply_record(self, mutation: RecordMutation) -> None:
        """应用 Record 变更。

        校验规则：
        1. lane 必须存在
        2. ID 不能重复

        特殊处理：
        - operation_started：添加到 open_operations
        - operation_finished：从 open_operations 移除

        Args:
            mutation: Record 变更

        Raises:
            SessionError: 如果校验失败
        """
        record = mutation.record

        # 校验 1：lane 必须存在
        if record.lane not in self._lanes:
            raise SessionError("invalid_lane", f"missing lane {record.lane}")

        # 校验 2：ID 不能重复
        if record.id in self._used_ids:
            raise SessionError("already_exists", f"duplicate id {record.id}")

        # 应用变更
        self._sequence = record.seq  # 更新序列号
        self._used_ids.add(record.id)  # 记录已使用的 ID
        self._records.append(record)  # 添加到 Record 列表

        # 特殊处理：操作生命周期管理
        if record.type == "operation_started":
            self._open_operations.setdefault(record.lane, {})[record.id] = record
        elif record.type == "operation_finished":
            self._open_operations.get(record.lane, {}).pop(record.run_id, None)

        self._log.append({"kind": "record", "seq": record.seq, "record": record})  # 记录日志

    def _apply_lane(self, mutation: LaneMutation) -> None:
        """应用 Lane 变更。

        校验规则：
        1. leaf_id 必须存在（如果指定）

        Args:
            mutation: Lane 变更

        Raises:
            SessionError: 如果校验失败
        """
        # 校验：leaf_id 必须存在
        if mutation.leaf_id is not None and mutation.leaf_id not in self._entries_by_id:
            raise SessionError("invalid_lane", f"missing lane target {mutation.leaf_id}")

        # 应用变更
        self._sequence = mutation.seq  # 更新序列号
        self._lanes[mutation.lane] = mutation.leaf_id  # 更新 lane 的叶子节点
        self._log.append({"kind": "lane", "seq": mutation.seq, "lane": mutation.lane, "leafId": mutation.leaf_id})  # 记录日志

    def _apply_name(self, mutation: NameFactMutation) -> None:
        """应用名称事实变更。

        用于更新会话名称。

        Args:
            mutation: 名称事实变更
        """
        self._sequence = mutation.seq  # 更新序列号
        self._name = mutation.name  # 更新会话名称
        self._log.append({"kind": "fact", "seq": mutation.seq, "fact": "name", "name": mutation.name})  # 记录日志

    def _apply_label(self, mutation: LabelFactMutation) -> None:
        """应用标签事实变更。

        用于为 Entry 添加或删除标签。

        校验规则：
        1. target_id 必须存在

        Args:
            mutation: 标签事实变更

        Raises:
            SessionError: 如果校验失败
        """
        # 校验：target_id 必须存在
        if mutation.target_id not in self._entries_by_id:
            raise SessionError("not_found", f"missing label target {mutation.target_id}")

        # 应用变更
        self._sequence = mutation.seq  # 更新序列号
        if mutation.label is None:
            self._labels.pop(mutation.target_id, None)  # 删除标签
        else:
            self._labels[mutation.target_id] = mutation.label  # 添加标签
        self._log.append({"kind": "fact", "seq": mutation.seq, "fact": "label", "targetId": mutation.target_id, "label": mutation.label})  # 记录日志

    # ============ 查询 ============

    def get_entry(self, entry_id: str) -> Entry | None:
        """根据 ID 获取 Entry。

        Args:
            entry_id: Entry 的 ID

        Returns:
            Entry 或 None（如果不存在）
        """
        return self._entries_by_id.get(entry_id)

    def find_entries(self, entry_type: str | None = None, order: str = "newestFirst", limit: int | None = None) -> list[Entry]:
        """查找 Entry，支持类型过滤、排序、限制数量。

        Args:
            entry_type: Entry 类型过滤（如 "message"、"compaction"）
            order: 排序方式（"newestFirst" 或 "oldestFirst"）
            limit: 最大返回数量

        Returns:
            Entry 列表
        """
        candidates = self._entries
        if entry_type:
            candidates = [e for e in candidates if e.type == entry_type]
        if order == "newestFirst":
            candidates = list(reversed(candidates))
        if limit:
            candidates = candidates[:limit]
        return candidates

    def get_entries_after(self, entry_id: str) -> list[Entry]:
        """获取指定 Entry 之后的所有 Entry。

        用于增量获取对话历史。

        Args:
            entry_id: 起始 Entry 的 ID

        Returns:
            Entry 列表（按顺序）
        """
        if entry_id not in self._entries_by_id:
            return []
        idx = next(i for i, e in enumerate(self._entries) if e.id == entry_id)
        return self._entries[idx + 1:]

    def get_records(self) -> list[LaneRecord]:
        """获取所有 Record。

        Returns:
            Record 列表（按顺序）
        """
        return self._records

    def get_log(self) -> list[dict]:
        """获取操作日志。

        Returns:
            日志列表（按顺序）
        """
        return self._log

    def get_stats(self) -> SessionStats:
        """获取会话统计。

        Returns:
            会话统计信息
        """
        return self._stats

    def get_name(self) -> str | None:
        """获取会话名称。

        Returns:
            会话名称或 None
        """
        return self._name

    def get_label(self, entry_id: str) -> str | None:
        """获取 Entry 的标签。

        Args:
            entry_id: Entry 的 ID

        Returns:
            标签内容或 None
        """
        return self._labels.get(entry_id)

    def get_sequence(self) -> int:
        """获取当前序列号。

        Returns:
            当前序列号
        """
        return self._sequence