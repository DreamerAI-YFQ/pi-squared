"""
会话门面（对应 pi 的 harness/session/session.ts）。

Session 是面向使用者的薄封装，把操作委托给 SessionStorage 接口。
真正的 seq/parentId/timestamp 分配和落盘由 storage（memory/jsonl）完成。

设计目标：
1. 提供统一的会话操作接口
2. 隐藏底层存储实现细节
3. 支持多种存储后端（内存/JSONL/数据库）

核心设计：
- SessionStorage 接口：定义存储操作的标准接口
- Session 类：门面封装，委托给具体存储实现
- 存储可替换：可以随时切换 memory/jsonl/数据库

类比：
- Session = 服务的总台（面向客户）
- SessionStorage = 不同的服务台（内存服务台/文件服务台/数据库服务台）
- 客户只需要找总台，总台会调用具体的服务台
"""
import uuid
from typing import Protocol

from pi_agent.harness.session.types import (
    Entry,
    LaneRecord,
    MessageEntry,
    SessionMetadata,
    SessionStats,
)


class SessionStorage(Protocol):
    """会话存储接口（对应 pi 的 SessionStorage）。

    定义了存储后端必须实现的标准接口。
    memory.py 和 jsonl.py 都实现这个接口，可以互相替换。

    核心方法：
    - get_metadata：获取会话元数据
    - append_entry：添加 Entry
    - append_record：添加 Record
    - get_entry：根据 ID 获取 Entry
    - find_entries：查找所有 Entry
    - find_records：查找所有 Record
    - get_stats：获取统计信息
    - create_lane：创建轨道
    - find_lanes：查找所有轨道
    """

    async def get_metadata(self) -> SessionMetadata: ...
    async def append_entry(self, entry: Entry, lane: str) -> Entry: ...
    async def append_record(self, record: LaneRecord) -> LaneRecord: ...
    async def get_entry(self, entry_id: str) -> Entry | None: ...
    async def find_entries(self) -> list[Entry]: ...
    async def find_records(self) -> list[LaneRecord]: ...
    async def get_stats(self) -> SessionStats: ...
    async def create_lane(self, lane: str, leaf_id: str | None = None) -> None: ...
    async def find_lanes(self) -> dict[str, str | None]: ...


class Session:
    """会话门面：封装 storage，提供 append/查询 API。

    核心职责：
    1. 提供统一的会话操作接口
    2. 隐藏底层存储实现细节
    3. 委托操作给 SessionStorage 实现

    特点：
    - 薄封装：不做额外逻辑，直接委托
    - 可替换：底层存储可以随意切换
    - 简单易用：提供高层 API，隐藏复杂性

    使用方式：
    ```python
    # 创建内存存储
    storage = InMemorySessionStorage(metadata)
    session = Session(storage)

    # 或创建 JSONL 存储
    storage = JsonlSessionStorage.create("session.jsonl")
    session = Session(storage)

    # 两种方式的使用接口完全一致
    await session.append_message(message)
    ```
    """

    def __init__(self, storage: SessionStorage, id_generator=None):
        """初始化会话门面。

        Args:
            storage: 存储后端实现（必须是 SessionStorage 接口）
            id_generator: ID 生成器（可选，默认用 UUID）
        """
        self._storage = storage  # 存储后端
        self._id_generator = id_generator or (lambda: str(uuid.uuid4()))  # ID 生成器

    async def get_metadata(self) -> SessionMetadata:
        """获取会话元数据。

        Returns:
            会话元数据
        """
        return await self._storage.get_metadata()

    async def append_message(self, message, lane: str = "main") -> str:
        """追加一条消息到指定 lane，返回 entry id。

        这是便捷方法，自动创建 MessageEntry 并添加。

        Args:
            message: 消息内容
            lane: 轨道标识（默认为 "main"）

        Returns:
            新创建的 Entry 的 ID
        """
        entry = MessageEntry(message=message, id=self._id_generator())
        result = await self._storage.append_entry(entry, lane)
        return result.id

    async def append_entry(self, entry: Entry, lane: str = "main") -> Entry:
        """追加一个 Entry 到会话中。

        Args:
            entry: 要添加的 Entry
            lane: 轨道标识（默认为 "main"）

        Returns:
            添加后的 Entry（已填充元数据）
        """
        return await self._storage.append_entry(entry, lane)

    async def append_record(self, record: LaneRecord) -> LaneRecord:
        """追加一个 Record 到会话中。

        Args:
            record: 要添加的 Record

        Returns:
            添加后的 Record（已填充元数据）
        """
        return await self._storage.append_record(record)

    async def create_lane(self, lane: str, leaf_id: str | None = None) -> None:
        """创建（或切换）一个 lane，leaf_id 指定分支起点。

        Args:
            lane: 轨道标识
            leaf_id: 叶子节点 ID（可选，指定分支起点）
        """
        await self._storage.create_lane(lane, leaf_id)

    async def find_lanes(self) -> dict[str, str | None]:
        """返回各 lane 及其当前叶子 entry id。

        Returns:
            轨道字典（lane → leaf_id）
        """
        return await self._storage.find_lanes()

    async def get_entry(self, entry_id: str) -> Entry | None:
        """根据 ID 获取 Entry。

        Args:
            entry_id: Entry 的 ID

        Returns:
            Entry 或 None（如果不存在）
        """
        return await self._storage.get_entry(entry_id)

    async def find_entries(self) -> list[Entry]:
        """查找所有 Entry。

        Returns:
            Entry 列表
        """
        return await self._storage.find_entries()

    async def find_records(self) -> list[LaneRecord]:
        """查找所有 Record。

        Returns:
            Record 列表
        """
        return await self._storage.find_records()

    async def get_stats(self) -> SessionStats:
        """获取会话统计。

        Returns:
            会话统计信息
        """
        return await self._storage.get_stats()
