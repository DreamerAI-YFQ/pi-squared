"""JSONL 编解码（对应 pi 的 jsonl/codec.ts）。

完整版：7 种 Entry + 9 种 Record 的编解码。字段名用 snake_case。
"""
import json
from dataclasses import asdict

from pydantic import TypeAdapter

from pi_agent.harness.session import types as t
from pi_agent.types import Message

_message_adapter = TypeAdapter(Message)


# ============ Entry 编解码 ============

def _entry_common(entry: t.Entry) -> dict:
    return {
        "kind": "entry",
        "id": entry.id,
        "seq": entry.seq,
        "parent_id": entry.parent_id,
        "timestamp": entry.timestamp,
        "type": entry.type,
    }


def _entry_to_dict(entry: t.Entry) -> dict:
    d = _entry_common(entry)
    if entry.type == "message":
        d["message"] = _message_adapter.dump_python(entry.message)
    elif entry.type == "model_change":
        d["provider"] = entry.provider
        d["model_id"] = entry.model_id
    elif entry.type == "thinking_level_change":
        d["thinking_level"] = entry.thinking_level
    elif entry.type == "active_tools_change":
        d["active_tool_names"] = entry.active_tool_names
    elif entry.type == "compaction":
        d["summary"] = entry.summary
        d["retained_tail"] = [_message_adapter.dump_python(m) for m in entry.retained_tail]
        d["tokens_before"] = entry.tokens_before
        if entry.details is not None:
            d["details"] = entry.details
    elif entry.type == "branch_summary":
        d["from_id"] = entry.from_id
        d["summary"] = entry.summary
        if entry.details is not None:
            d["details"] = entry.details
    elif entry.type == "custom":
        d["custom_type"] = entry.custom_type
        if entry.data is not None:
            d["data"] = entry.data
    return d


def _dict_to_entry(d: dict) -> t.Entry:
    common = dict(
        id=d["id"], seq=d["seq"], parent_id=d.get("parent_id"), timestamp=d["timestamp"],
    )
    entry_type = d["type"]
    if entry_type == "message":
        return t.MessageEntry(message=_message_adapter.validate_python(d["message"]), **common)
    if entry_type == "model_change":
        return t.ModelChangeEntry(provider=d["provider"], model_id=d["model_id"], **common)
    if entry_type == "thinking_level_change":
        return t.ThinkingLevelEntry(thinking_level=d["thinking_level"], **common)
    if entry_type == "active_tools_change":
        return t.ActiveToolsEntry(active_tool_names=d["active_tool_names"], **common)
    if entry_type == "compaction":
        return t.CompactionEntry(
            summary=d["summary"],
            retained_tail=[_message_adapter.validate_python(m) for m in d["retained_tail"]],
            tokens_before=d["tokens_before"],
            details=d.get("details"),
            **common,
        )
    if entry_type == "branch_summary":
        return t.BranchSummaryEntry(from_id=d["from_id"], summary=d["summary"], details=d.get("details"), **common)
    if entry_type == "custom":
        return t.CustomEntry(custom_type=d["custom_type"], data=d.get("data"), **common)
    raise ValueError(f"unknown entry type: {entry_type}")


def encode_entry(entry: t.Entry, lane: str | None = None) -> str:
    d = _entry_to_dict(entry)
    if lane is not None:
        d["lane"] = lane
    return json.dumps(d, ensure_ascii=False) + "\n"


def parse_entry(line: str) -> t.Entry:
    return _dict_to_entry(json.loads(line))


# ============ Record 编解码 ============

_RECORD_CLASSES = {
    "operation_started": t.OperationStartedRecord,
    "abort_requested": t.AbortRequestedRecord,
    "operation_finished": t.OperationFinishedRecord,
    "step_attempt": t.StepAttemptRecord,
    "tool_started": t.ToolStartedRecord,
    "queue_enqueued": t.QueueEnqueuedRecord,
    "queue_cancelled": t.QueueCancelledRecord,
    "write_deferred": t.WriteDeferredRecord,
    "usage": t.UsageRecord,
}


def _record_to_dict(record: t.LaneRecord) -> dict:
    d = asdict(record)
    d["kind"] = "record"
    return d


def _dict_to_record(d: dict) -> t.LaneRecord:
    cls = _RECORD_CLASSES[d["type"]]
    kwargs = {k: v for k, v in d.items() if k != "kind"}
    return cls(**kwargs)


def encode_record(record: t.LaneRecord) -> str:
    return json.dumps(_record_to_dict(record), ensure_ascii=False) + "\n"


def parse_record(line: str) -> t.LaneRecord:
    return _dict_to_record(json.loads(line))


# ============ Lane 编解码 ============

def encode_lane(seq: int, lane: str, leaf_id: str | None) -> str:
    """把「创建/切换 lane」编成一行 jsonl。"""
    return json.dumps(
        {"kind": "lane", "seq": seq, "lane": lane, "leaf_id": leaf_id},
        ensure_ascii=False,
    ) + "\n"
