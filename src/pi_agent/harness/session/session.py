"""会话门面（对应 pi 的 harness/session/session.ts）。

Session 是面向使用者的薄封装，把操作委托给 SessionStorage 接口。
真正的 seq/parentId/timestamp 分配和落盘由 storage（memory/jsonl）完成。
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
    """会话存储接口（对应 pi 的 SessionStorage）。memory 和 jsonl 都实现它。"""

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
    """会话门面：封装 storage，提供 append/查询 API。"""

    def __init__(self, storage: SessionStorage, id_generator=None):
        self._storage = storage
        self._id_generator = id_generator or (lambda: str(uuid.uuid4()))

    async def get_metadata(self) -> SessionMetadata:
        return await self._storage.get_metadata()

    async def append_message(self, message, lane: str = "main") -> str:
        """追加一条消息到指定 lane，返回 entry id。"""
        entry = MessageEntry(message=message, id=self._id_generator())
        result = await self._storage.append_entry(entry, lane)
        return result.id

    async def append_entry(self, entry: Entry, lane: str = "main") -> Entry:
        return await self._storage.append_entry(entry, lane)

    async def append_record(self, record: LaneRecord) -> LaneRecord:
        return await self._storage.append_record(record)

    async def create_lane(self, lane: str, leaf_id: str | None = None) -> None:
        """创建（或切换）一个 lane，leaf_id 指定分支起点。"""
        await self._storage.create_lane(lane, leaf_id)

    async def find_lanes(self) -> dict[str, str | None]:
        """返回各 lane 及其当前叶子 entry id。"""
        return await self._storage.find_lanes()

    async def get_entry(self, entry_id: str) -> Entry | None:
        return await self._storage.get_entry(entry_id)

    async def find_entries(self) -> list[Entry]:
        return await self._storage.find_entries()

    async def find_records(self) -> list[LaneRecord]:
        return await self._storage.find_records()

    async def get_stats(self) -> SessionStats:
        return await self._storage.get_stats()
