"""会话状态机（对应 pi 的 harness/session/state.ts）。

核心：维护 entries/records/lanes/log/stats，校验并应用 mutation。
mutation 是"追加日志"的单位，seq 必须连续（重放恢复的基础）。
"""
from dataclasses import dataclass
from typing import Any, Literal, Union

from pi_agent.harness.session.types import (
    Entry,
    LaneRecord,
    OperationStartedRecord,
    SessionStats,
)


class SessionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class EntryMutation:
    entry: Entry
    lane: str | None = None
    kind: Literal["entry"] = "entry"


@dataclass
class RecordMutation:
    record: LaneRecord
    kind: Literal["record"] = "record"


@dataclass
class LaneMutation:
    seq: int
    lane: str
    leaf_id: str | None
    kind: Literal["lane"] = "lane"


@dataclass
class NameFactMutation:
    seq: int
    name: str | None
    kind: Literal["fact_name"] = "fact_name"


@dataclass
class LabelFactMutation:
    seq: int
    target_id: str
    label: str | None
    kind: Literal["fact_label"] = "fact_label"


SessionMutation = Union[
    EntryMutation, RecordMutation, LaneMutation, NameFactMutation, LabelFactMutation
]


class SessionState:
    def __init__(self):
        self._sequence = 0
        self._used_ids: set[str] = set()
        self._entries: list[Entry] = []
        self._entries_by_id: dict[str, Entry] = {}
        self._records: list[LaneRecord] = []
        self._open_operations: dict[str, dict[str, OperationStartedRecord]] = {}
        self._lanes: dict[str, str | None] = {"main": None}
        self._log: list[dict] = []
        self._stats = SessionStats()
        self._name: str | None = None
        self._labels: dict[str, str] = {}

    # ============ mutation 应用 ============

    def apply_mutation(self, mutation: SessionMutation) -> None:
        if mutation.kind == "entry":
            seq = mutation.entry.seq
        elif mutation.kind == "record":
            seq = mutation.record.seq
        else:
            seq = mutation.seq

        if seq != self._sequence + 1:
            raise SessionError("invalid_entry", f"non-consecutive seq {seq}")

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
        entry = mutation.entry
        if entry.id in self._used_ids:
            raise SessionError("already_exists", f"duplicate id {entry.id}")
        if mutation.lane is not None:
            leaf_id = self._lanes.get(mutation.lane)
            if leaf_id is None and mutation.lane not in self._lanes:
                raise SessionError("invalid_lane", f"missing lane {mutation.lane}")
            if entry.parent_id != leaf_id:
                raise SessionError("invalid_entry", "entry does not chain to the lane leaf")
        if entry.parent_id is not None and entry.parent_id not in self._entries_by_id:
            raise SessionError("invalid_entry", f"missing parent {entry.parent_id}")

        self._sequence = entry.seq
        self._used_ids.add(entry.id)
        self._entries.append(entry)
        self._entries_by_id[entry.id] = entry
        if mutation.lane is not None:
            self._lanes[mutation.lane] = entry.id
        self._log.append({"kind": "entry", "seq": entry.seq, "entry": entry})
        if entry.type == "message":
            self._stats.message_count += 1

    def _apply_record(self, mutation: RecordMutation) -> None:
        record = mutation.record
        if record.lane not in self._lanes:
            raise SessionError("invalid_lane", f"missing lane {record.lane}")
        if record.id in self._used_ids:
            raise SessionError("already_exists", f"duplicate id {record.id}")

        self._sequence = record.seq
        self._used_ids.add(record.id)
        self._records.append(record)
        if record.type == "operation_started":
            self._open_operations.setdefault(record.lane, {})[record.id] = record
        elif record.type == "operation_finished":
            self._open_operations.get(record.lane, {}).pop(record.run_id, None)
        self._log.append({"kind": "record", "seq": record.seq, "record": record})

    def _apply_lane(self, mutation: LaneMutation) -> None:
        if mutation.leaf_id is not None and mutation.leaf_id not in self._entries_by_id:
            raise SessionError("invalid_lane", f"missing lane target {mutation.leaf_id}")
        self._sequence = mutation.seq
        self._lanes[mutation.lane] = mutation.leaf_id
        self._log.append({"kind": "lane", "seq": mutation.seq, "lane": mutation.lane, "leafId": mutation.leaf_id})

    def _apply_name(self, mutation: NameFactMutation) -> None:
        self._sequence = mutation.seq
        self._name = mutation.name
        self._log.append({"kind": "fact", "seq": mutation.seq, "fact": "name", "name": mutation.name})

    def _apply_label(self, mutation: LabelFactMutation) -> None:
        if mutation.target_id not in self._entries_by_id:
            raise SessionError("not_found", f"missing label target {mutation.target_id}")
        self._sequence = mutation.seq
        if mutation.label is None:
            self._labels.pop(mutation.target_id, None)
        else:
            self._labels[mutation.target_id] = mutation.label
        self._log.append({"kind": "fact", "seq": mutation.seq, "fact": "label", "targetId": mutation.target_id, "label": mutation.label})

    # ============ 查询 ============

    def get_entry(self, entry_id: str) -> Entry | None:
        return self._entries_by_id.get(entry_id)

    def find_entries(self, entry_type: str | None = None, order: str = "newestFirst", limit: int | None = None) -> list[Entry]:
        entries = self._entries if order == "oldestFirst" else list(reversed(self._entries))
        result = []
        for entry in entries:
            if entry_type is not None and entry.type != entry_type:
                continue
            result.append(entry)
            if limit is not None and len(result) >= limit:
                break
        return result

    def find_records(self, lane: str | None = None, record_type: str | None = None) -> list[LaneRecord]:
        result = []
        for record in reversed(self._records):
            if lane is not None and record.lane != lane:
                continue
            if record_type is not None and record.type != record_type:
                continue
            result.append(record)
        return result

    def find_open_operations(self, lane: str, limit: int | None = None) -> list[OperationStartedRecord]:
        ops = list(reversed(list(self._open_operations.get(lane, {}).values())))
        return ops if limit is None else ops[:limit]

    def get_log(self) -> list[dict]:
        return list(self._log)

    def get_name(self) -> str | None:
        return self._name

    def get_stats(self) -> SessionStats:
        return self._stats

    @property
    def next_sequence(self) -> int:
        return self._sequence + 1

    def require_lane(self, lane: str) -> str | None:
        if lane not in self._lanes:
            raise SessionError("invalid_lane", f"Lane not found: {lane}")
        return self._lanes[lane]

    def find_lanes(self) -> dict[str, str | None]:
        return dict(self._lanes)
