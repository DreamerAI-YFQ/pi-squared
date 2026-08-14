"""JSONL 磁盘后端（对应 pi 的 jsonl/storage.ts 简化版）。

核心：追加写盘 + 重放恢复。每次 append 既更新内存 state，又追加一行 jsonl；
open 时逐行重放到 state，还原会话。
"""
import json
import time
import uuid

from pi_agent.harness.session.jsonl import encode_entry, encode_lane, encode_record, parse_entry, parse_record
from pi_agent.harness.session.state import EntryMutation, LaneMutation, RecordMutation, SessionState
from pi_agent.harness.session.types import Entry, LaneRecord, SessionMetadata, SessionStats


def _now_ms() -> int:
    return int(time.time() * 1000)


class JsonlSessionStorage:
    def __init__(self, path: str, metadata: SessionMetadata):
        self._path = path
        self._metadata = metadata
        self._state = SessionState()

    @classmethod
    def create(cls, path: str, session_id: str | None = None) -> "JsonlSessionStorage":
        session_id = session_id or str(uuid.uuid4())
        metadata = SessionMetadata(id=session_id, created_at=_now_ms())
        header = {
            "kind": "header",
            "version": 4,
            "id": session_id,
            "createdAt": metadata.created_at,
        }
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(header) + "\n")
        return cls(path, metadata)

    @classmethod
    def open(cls, path: str) -> "JsonlSessionStorage":
        storage = cls.__new__(cls)
        storage._path = path
        storage._state = SessionState()
        metadata = SessionMetadata(id="", created_at=0)
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if d.get("kind") == "header":
                    metadata = SessionMetadata(id=d["id"], created_at=d["createdAt"])
                    continue
                if d.get("kind") == "entry":
                    entry = parse_entry(line)
                    storage._state.apply_mutation(EntryMutation(entry=entry, lane=d.get("lane")))
                elif d.get("kind") == "record":
                    record = parse_record(line)
                    storage._state.apply_mutation(RecordMutation(record=record))
                elif d.get("kind") == "lane":
                    storage._state.apply_mutation(
                        LaneMutation(seq=d["seq"], lane=d["lane"], leaf_id=d.get("leaf_id"))
                    )
        storage._metadata = metadata
        return storage

    async def get_metadata(self) -> SessionMetadata:
        return self._metadata

    async def append_entry(self, entry: Entry, lane: str) -> Entry:
        entry.id = entry.id or str(uuid.uuid4())
        entry.seq = self._state.next_sequence
        entry.parent_id = self._state.require_lane(lane)
        entry.timestamp = _now_ms()
        self._state.apply_mutation(EntryMutation(entry=entry, lane=lane))
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(encode_entry(entry, lane))
        return entry

    async def append_record(self, record: LaneRecord) -> LaneRecord:
        record.id = record.id or str(uuid.uuid4())
        record.seq = self._state.next_sequence
        record.timestamp = _now_ms()
        self._state.apply_mutation(RecordMutation(record=record))
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(encode_record(record))
        return record

    async def create_lane(self, lane: str, leaf_id: str | None = None) -> None:
        seq = self._state.next_sequence
        self._state.apply_mutation(LaneMutation(seq=seq, lane=lane, leaf_id=leaf_id))
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(encode_lane(seq, lane, leaf_id))

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
