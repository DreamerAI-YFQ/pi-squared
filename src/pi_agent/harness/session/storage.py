"""
JSONL 磁盘后端（对应 pi 的 jsonl/storage.ts 简化版）。

核心：追加写盘 + 重放恢复。每次 append 既更新内存 state，又追加一行 jsonl；
open 时逐行重放到 state，还原会话。

设计目标：
1. 持久化存储：对话数据写入 JSONL 文件，重启后不丢失
2. 崩溃恢复：从 JSONL 文件重放，还原会话状态
3. 统一接口：与 InMemorySessionStorage 提供相同的接口

核心机制：
- 写入：更新内存状态 + 追加到文件末尾
- 读取：逐行解析 JSONL，重放到状态机

类比：
- 就像记账本：每笔交易记到账本上（追加写盘）
- 查账时：从头到尾逐笔重放，恢复账本状态（重放恢复）
"""
import json
import time
import uuid

from pi_agent.harness.session.jsonl import encode_entry, encode_lane, encode_record, parse_entry, parse_record
from pi_agent.harness.session.state import EntryMutation, LaneMutation, RecordMutation, SessionState
from pi_agent.harness.session.types import Entry, LaneRecord, SessionMetadata, SessionStats


def _now_ms() -> int:
    """获取当前时间戳（毫秒）。

    Returns:
        当前时间戳（毫秒）
    """
    return int(time.time() * 1000)


class JsonlSessionStorage:
    """JSONL 磁盘存储：实现会话的持久化存储。

    核心职责：
    1. 创建新会话：写入 JSONL 文件，包含 header
    2. 打开已有会话：逐行解析 JSONL，重放到状态机
    3. 追加操作：更新内存状态 + 追加到文件末尾
    4. 提供查询接口：与内存存储统一

    特点：
    - 数据持久化到磁盘，重启后不丢失
    - 支持崩溃恢复（重放日志）
    - 与 InMemorySessionStorage 接口统一
    """

    def __init__(self, path: str, metadata: SessionMetadata):
        """初始化 JSONL 存储。

        Args:
            path: JSONL 文件路径
            metadata: 会话元数据
        """
        self._path = path  # JSONL 文件路径
        self._metadata = metadata  # 会话元数据
        self._state = SessionState()  # 会话状态机

    @classmethod
    def create(cls, path: str, session_id: str | None = None) -> "JsonlSessionStorage":
        """创建一个新的 JSONL 会话文件。

        创建流程：
        1. 生成或使用提供的 session_id
        2. 创建会话元数据
        3. 写入 header（包含版本、ID、创建时间）
        4. 返回存储实例

        Args:
            path: JSONL 文件路径
            session_id: 会话 ID（可选，不传则自动生成）

        Returns:
            新创建的 JsonlSessionStorage 实例
        """
        session_id = session_id or str(uuid.uuid4())  # ID 自动生成
        metadata = SessionMetadata(id=session_id, created_at=_now_ms())  # 创建元数据

        # 写入 header（文件的第一行）
        header = {
            "kind": "header",  # 标记这是 header
            "version": 4,  # 版本号
            "id": session_id,  # 会话 ID
            "createdAt": metadata.created_at,  # 创建时间
        }

        # 写入文件
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(header) + "\n")

        return cls(path, metadata)

    @classmethod
    def open(cls, path: str) -> "JsonlSessionStorage":
        """打开已有的 JSONL 会话文件。

        打开流程：
        1. 逐行读取 JSONL 文件
        2. 跳过空行
        3. 解析每行，根据 kind 分发
        4. 重放到状态机，还原会话状态

        Args:
            path: JSONL 文件路径

        Returns:
            打开的 JsonlSessionStorage 实例
        """
        # 创建空实例（不调用 __init__）
        storage = cls.__new__(cls)
        storage._path = path
        storage._state = SessionState()  # 创建空状态机
        metadata = SessionMetadata(id="", created_at=0)  # 临时元数据

        # 逐行读取并重放
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue  # 跳过空行

                d = json.loads(line)  # 解析 JSON

                # 根据 kind 分发处理
                if d.get("kind") == "header":
                    # 提取 header 中的元数据
                    metadata = SessionMetadata(id=d["id"], created_at=d["createdAt"])
                    continue

                if d.get("kind") == "entry":
                    # 重放 Entry
                    entry = parse_entry(line)
                    storage._state.apply_mutation(EntryMutation(entry=entry, lane=d.get("lane")))
                elif d.get("kind") == "record":
                    # 重放 Record
                    record = parse_record(line)
                    storage._state.apply_mutation(RecordMutation(record=record))
                elif d.get("kind") == "lane":
                    # 重放 Lane
                    storage._state.apply_mutation(
                        LaneMutation(seq=d["seq"], lane=d["lane"], leaf_id=d.get("leaf_id"))
                    )

        storage._metadata = metadata  # 设置元数据
        return storage

    async def get_metadata(self) -> SessionMetadata:
        """获取会话元数据。

        Returns:
            会话元数据
        """
        return self._metadata

    async def append_entry(self, entry: Entry, lane: str) -> Entry:
        """添加一个 Entry 到会话中。

        操作流程：
        1. 自动分配 ID、seq、parent_id、timestamp
        2. 应用到状态机
        3. 追加到 JSONL 文件

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

        # 追加到文件
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(encode_entry(entry, lane))

        return entry

    async def append_record(self, record: LaneRecord) -> LaneRecord:
        """添加一个 Record 到会话中。

        操作流程：
        1. 自动分配 ID、seq、timestamp
        2. 应用到状态机
        3. 追加到 JSONL 文件

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

        # 追加到文件
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(encode_record(record))

        return record

    async def create_lane(self, lane: str, leaf_id: str | None = None) -> None:
        """创建一个新轨道。

        操作流程：
        1. 分配 seq
        2. 应用到状态机
        3. 追加到 JSONL 文件

        Args:
            lane: 轨道标识
            leaf_id: 叶子节点 ID（可选）
        """
        seq = self._state.next_sequence  # 分配 seq
        self._state.apply_mutation(LaneMutation(seq=seq, lane=lane, leaf_id=leaf_id))  # 应用到状态机

        # 追加到文件
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(encode_lane(seq, lane, leaf_id))

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
