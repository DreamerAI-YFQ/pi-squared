"""
JSONL 编解码（对应 pi 的 jsonl/codec.ts）。

完整版：7 种 Entry + 9 种 Record 的编解码。字段名用 snake_case。

设计目标：
1. 编码：把 Entry/Record 转成 JSONL 格式（每行一个 JSON）
2. 解码：从 JSONL 格式还原成 Entry/Record
3. 持久化：让对话数据可以存储到文件，重启后恢复

JSONL 格式：
- 每行一个 JSON 对象
- 适合增量写入（追加到文件末尾）
- 适合逐行读取（重放恢复）

类比：
- 编码 = 把对话内容写成日记
- 解码 = 读日记还原对话内容
- JSONL = 日记格式（每行一条记录）
"""
import json
from dataclasses import asdict

from pydantic import TypeAdapter

from pi_agent.harness.session import types as t
from pi_agent.types import Message

# Message 类型适配器：用于编解码 Message 对象
_message_adapter = TypeAdapter(Message)


# ============ Entry 编解码 ============
# Entry 有 7 种类型，每种都有特定的字段


def _entry_common(entry: t.Entry) -> dict:
    """提取 Entry 的公共字段。

    所有 Entry 都有这些字段：id、seq、parent_id、timestamp、type。

    Args:
        entry: Entry 对象

    Returns:
        包含公共字段的字典
    """
    return {
        "kind": "entry",  # 标记这是 Entry（区别于 Record）
        "id": entry.id,  # 节点唯一标识
        "seq": entry.seq,  # 序列号
        "parent_id": entry.parent_id,  # 父节点 ID
        "timestamp": entry.timestamp,  # 时间戳
        "type": entry.type,  # Entry 类型
    }


def _entry_to_dict(entry: t.Entry) -> dict:
    """把 Entry 编码成字典。

    根据 Entry 类型提取特定字段，组合成字典。

    Args:
        entry: Entry 对象

    Returns:
        编码后的字典
    """
    d = _entry_common(entry)  # 先提取公共字段

    # 根据类型提取特定字段
    if entry.type == "message":
        d["message"] = _message_adapter.dump_python(entry.message)  # 消息内容
    elif entry.type == "model_change":
        d["provider"] = entry.provider  # 提供商
        d["model_id"] = entry.model_id  # 模型 ID
    elif entry.type == "thinking_level_change":
        d["thinking_level"] = entry.thinking_level  # 思考级别
    elif entry.type == "active_tools_change":
        d["active_tool_names"] = entry.active_tool_names  # 启用的工具列表
    elif entry.type == "compaction":
        d["summary"] = entry.summary  # 压缩摘要
        d["retained_tail"] = [_message_adapter.dump_python(m) for m in entry.retained_tail]  # 保留的尾部消息
        d["tokens_before"] = entry.tokens_before  # 压缩前的 token 数
        if entry.details is not None:
            d["details"] = entry.details  # 其他详细信息
    elif entry.type == "branch_summary":
        d["from_id"] = entry.from_id  # 分支起始节点 ID
        d["summary"] = entry.summary  # 分支摘要
        if entry.details is not None:
            d["details"] = entry.details  # 其他详细信息
    elif entry.type == "custom":
        d["custom_type"] = entry.custom_type  # 自定义类型
        if entry.data is not None:
            d["data"] = entry.data  # 自定义数据

    return d


def _dict_to_entry(d: dict) -> t.Entry:
    """把字典解码成 Entry。

    根据 type 字段判断 Entry 类型，还原成对应的 Entry 对象。

    Args:
        d: 字典（从 JSONL 解析而来）

    Returns:
        Entry 对象

    Raises:
        ValueError: 如果 Entry 类型未知
    """
    # 提取公共字段
    common = dict(
        id=d["id"], seq=d["seq"], parent_id=d.get("parent_id"), timestamp=d["timestamp"],
    )

    # 根据 type 字段还原成对应类型的 Entry
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
    """把 Entry 编码成 JSONL 格式（一行 JSON）。

    Args:
        entry: Entry 对象
        lane: 轨道标识（可选）

    Returns:
        JSONL 格式的字符串（一行 JSON + 换行符）
    """
    d = _entry_to_dict(entry)  # 编码成字典
    if lane is not None:
        d["lane"] = lane  # 添加轨道信息
    return json.dumps(d, ensure_ascii=False) + "\n"  # 转成 JSON 字符串 + 换行符


def parse_entry(line: str) -> t.Entry:
    """从 JSONL 格式解析 Entry。

    Args:
        line: JSONL 行（一行 JSON 字符串）

    Returns:
        Entry 对象
    """
    return _dict_to_entry(json.loads(line))  # 解析 JSON 并还原成 Entry


# ============ Record 编解码 ============
# Record 有 9 种类型，每种都有特定的字段


# Record 类型到类的映射表
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
    """把 Record 编码成字典。

    使用 dataclasses.asdict 自动转换所有字段。

    Args:
        record: Record 对象

    Returns:
        编码后的字典
    """
    d = asdict(record)  # 自动转换所有字段
    d["kind"] = "record"  # 标记这是 Record（区别于 Entry）
    return d


def _dict_to_record(d: dict) -> t.LaneRecord:
    """把字典解码成 Record。

    根据 type 字段找到对应的类，还原成 Record 对象。

    Args:
        d: 字典（从 JSONL 解析而来）

    Returns:
        Record 对象
    """
    cls = _RECORD_CLASSES[d["type"]]  # 根据 type 找到对应的类
    kwargs = {k: v for k, v in d.items() if k != "kind"}  # 过滤掉 kind 字段
    return cls(**kwargs)  # 实例化 Record 对象


def encode_record(record: t.LaneRecord) -> str:
    """把 Record 编码成 JSONL 格式（一行 JSON）。

    Args:
        record: Record 对象

    Returns:
        JSONL 格式的字符串（一行 JSON + 换行符）
    """
    return json.dumps(_record_to_dict(record), ensure_ascii=False) + "\n"


def parse_record(line: str) -> t.LaneRecord:
    """从 JSONL 格式解析 Record。

    Args:
        line: JSONL 行（一行 JSON 字符串）

    Returns:
        Record 对象
    """
    return _dict_to_record(json.loads(line))  # 解析 JSON 并还原成 Record


# ============ Lane 编解码 ============
# Lane 变更也有对应的编解码


def encode_lane(seq: int, lane: str, leaf_id: str | None) -> str:
    """把「创建/切换 lane」编成一行 jsonl。

    Args:
        seq: 序列号
        lane: 轨道标识
        leaf_id: 叶子节点 ID

    Returns:
        JSONL 格式的字符串（一行 JSON + 换行符）
    """
    return json.dumps(
        {"kind": "lane", "seq": seq, "lane": lane, "leaf_id": leaf_id},
        ensure_ascii=False,
    ) + "\n"
