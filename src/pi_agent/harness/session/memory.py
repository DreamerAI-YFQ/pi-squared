"""内存版会话后端（对应 pi 的 memory.ts）。

把 SessionState 状态机包装成 SessionStorage 接口，负责分配 seq/parentId/timestamp。
"""
import time
import uuid

from pi_agent.harness.session.state import EntryMutation, LaneMutation, RecordMutation, SessionState
from pi_agent.harness.session.types import Entry, LaneRecord, SessionMetadata, SessionStats


def _now_ms() -> int:
    return int(time.time() * 1000)


class InMemorySessionStorage:
    def __init__(self, metadata: SessionMetadata):
        self._metadata = metadata
        self._state = SessionState()

    async def get_metadata(self) -> SessionMetadata:
        return self._metadata

    async def append_entry(self, entry: Entry, lane: str) -> Entry:
        entry.id = entry.id or str(uuid.uuid4())
        entry.seq = self._state.next_sequence
        entry.parent_id = self._state.require_lane(lane)
        entry.timestamp = _now_ms()
        self._state.apply_mutation(EntryMutation(entry=entry, lane=lane))
        return entry

    async def append_record(self, record: LaneRecord) -> LaneRecord:
        record.id = record.id or str(uuid.uuid4())
        record.seq = self._state.next_sequence
        record.timestamp = _now_ms()
        self._state.apply_mutation(RecordMutation(record=record))
        return record

    async def create_lane(self, lane: str, leaf_id: str | None = None) -> None:
        self._state.apply_mutation(
            LaneMutation(seq=self._state.next_sequence, lane=lane, leaf_id=leaf_id)
        )

    async def find_lanes(self) -> dict[str, str | None]:
        return self._state.find_lanes()

    async def get_entry(self, entry_id: str) -> Entry | None:
        return self._state.get_entry(entry_id)

    async def find_entries(self) -> list[Entry]:
        return self._state.find_entries()

    async def find_records(self) -> list[LaneRecord]:
        return self._state.find_records()

    async def get_stats(self) -> SessionStats:
        return self._state.get_stats()


class InMemorySessionRepo:
    """内存版会话仓库：create / open / list。"""

    def __init__(self):
        self._sessions: dict[str, InMemorySessionStorage] = {}

    async def create(self, session_id: str | None = None) -> InMemorySessionStorage:
        session_id = session_id or str(uuid.uuid4())
        metadata = SessionMetadata(id=session_id, created_at=_now_ms())
        storage = InMemorySessionStorage(metadata)
        self._sessions[session_id] = storage
        return storage

    async def open(self, session_id: str) -> InMemorySessionStorage:
        if session_id not in self._sessions:
            raise KeyError(f"Session not found: {session_id}")
        return self._sessions[session_id]

    async def list(self) -> list[str]:
        return list(self._sessions.keys())
