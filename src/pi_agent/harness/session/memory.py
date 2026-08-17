"""
内存版会话后端（对应 pi 的 memory.ts）。

把 SessionState 状态机包装成 SessionStorage 接口，负责分配 seq/parentId/timestamp。

设计目标：
1. 提供内存存储：对话存在内存里，重启后丢失
2. 自动分配元数据：ID、seq、timestamp 自动生成
3. 实现 SessionStorage 接口：与其他存储后端（如 JSONL）统一接口

使用场景：
- 开发测试：不需要真正的持久化
- 快速原型：临时验证功能
- 单进程应用：不需要跨进程共享

限制：
- 重启后数据丢失
- 不适合生产环境
- 不支持跨进程访问
"""
import time
import uuid

from pi_agent.harness.session.state import EntryMutation, LaneMutation, RecordMutation, SessionState
from pi_agent.harness.session.types import Entry, LaneRecord, SessionMetadata, SessionStats


def _now_ms() -> int:
    """获取当前时间戳（毫秒）。

    Returns:
        当前时间戳（毫秒）
    """
    return int(time.time() * 1000)


class InMemorySessionStorage:
    """内存版会话存储：包装 SessionState 实现 SessionStorage 接口。

    核心职责：
    1. 维护 SessionState 状态机
    2. 自动分配 ID、seq、timestamp
    3. 实现 SessionStorage 接口（与 JSONL 等其他后端统一）

    特点：
    - 数据存在内存里，重启后丢失
    - 自动分配元数据，不需要手动管理
    - 适合开发测试，不适合生产环境
    """

    def __init__(self, metadata: SessionMetadata):
        """初始化内存会话存储。

        Args:
            metadata: 会话元数据（ID、创建时间等）
        """
        self._metadata = metadata  # 会话元数据
        self._state = SessionState()  # 会话状态机

    async def get_metadata(self) -> SessionMetadata:
        """获取会话元数据。

        Returns:
            会话元数据
        """
        return self._metadata

    async def append_entry(self, entry: Entry, lane: str) -> Entry:
        """添加一个 Entry 到会话中。

        自动分配 ID、seq、parent_id、timestamp。

        Args:
            entry: 要添加的 Entry
            lane: 轨道标识

        Returns:
            添加后的 Entry（已填充元数据）
        """
        # 自动分配元数据
        entry.id = entry.id or str(uuid.uuid4())  # ID 自动生成
        entry.seq = self._state.next_sequence  # seq 自动分配
        entry.parent_id = self._state.require_lane(lane)  # parent_id 从 lane 获取
        entry.timestamp = _now_ms()  # timestamp 自动生成

        # 应用到状态机
        self._state.apply_mutation(EntryMutation(entry=entry, lane=lane))
        return entry

    async def append_record(self, record: LaneRecord) -> LaneRecord:
        """添加一个 Record 到会话中。

        自动分配 ID、seq、timestamp。

        Args:
            record: 要添加的 Record

        Returns:
            添加后的 Record（已填充元数据）
        """
        # 自动分配元数据
        record.id = record.id or str(uuid.uuid4())  # ID 自动生成
        record.seq = self._state.next_sequence  # seq 自动分配
        record.timestamp = _now_ms()  # timestamp 自动生成

        # 应用到状态机
        self._state.apply_mutation(RecordMutation(record=record))
        return record

    async def create_lane(self, lane: str, leaf_id: str | None = None) -> None:
        """创建一个新轨道。

        Args:
            lane: 轨道标识
            leaf_id: 叶子节点 ID（可选）
        """
        self._state.apply_mutation(
            LaneMutation(seq=self._state.next_sequence, lane=lane, leaf_id=leaf_id)
        )

    async def find_lanes(self) -> dict[str, str | None]:
        """查找所有轨道。

        Returns:
            轨道字典（lane → leaf_id）
        """
        return self._state.find_lanes()

    async def get_entry(self, entry_id: str) -> Entry | None:
        """根据 ID 获取 Entry。

        Args:
            entry_id: Entry 的 ID

        Returns:
            Entry 或 None（如果不存在）
        """
        return self._state.get_entry(entry_id)

    async def find_entries(self) -> list[Entry]:
        """查找所有 Entry。

        Returns:
            Entry 列表
        """
        return self._state.find_entries()

    async def find_records(self) -> list[LaneRecord]:
        """查找所有 Record。

        Returns:
            Record 列表
        """
        return self._state.find_records()

    async def get_stats(self) -> SessionStats:
        """获取会话统计。

        Returns:
            会话统计信息
        """
        return self._state.get_stats()


class InMemorySessionRepo:
    """内存版会话仓库：管理多个会话的创建/打开/列表。

    核心职责：
    1. 创建新会话
    2. 打开已有会话
    3. 列出所有会话

    特点：
    - 所有会话存在内存里
    - 重启后所有会话丢失
    - 适合开发测试
    """

    def __init__(self):
        """初始化会话仓库。"""
        self._sessions: dict[str, InMemorySessionStorage] = {}  # 会话字典（session_id → storage）

    async def create(self, session_id: str | None = None) -> InMemorySessionStorage:
        """创建一个新会话。

        Args:
            session_id: 会话 ID（可选，不传则自动生成）

        Returns:
            新创建的会话存储
        """
        session_id = session_id or str(uuid.uuid4())  # ID 自动生成
        metadata = SessionMetadata(id=session_id, created_at=_now_ms())  # 创建元数据
        storage = InMemorySessionStorage(metadata)  # 创建存储
        self._sessions[session_id] = storage  # 存入字典
        return storage

    async def open(self, session_id: str) -> InMemorySessionStorage:
        """打开一个已有会话。

        Args:
            session_id: 会话 ID

        Returns:
            会话存储

        Raises:
            KeyError: 如果会话不存在
        """
        if session_id not in self._sessions:
            raise KeyError(f"Session not found: {session_id}")
        return self._sessions[session_id]

    async def list(self) -> list[str]:
        """列出所有会话 ID。

        Returns:
            会话 ID 列表
        """
        return list(self._sessions.keys())
