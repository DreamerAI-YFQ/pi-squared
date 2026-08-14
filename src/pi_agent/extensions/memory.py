"""长期记忆（对应 ETCLOVG 的 C 层，特色实现）。

跨会话记忆的三个环节：写入（提取） -> 存储（持久化） -> 检索（相关性）。

- 提取：从会话消息里挑出值得记住的内容，做成「记忆条目 Memory」。
- 存储：条目落盘，让记忆跨会话存活（JsonMemoryStore）。
- 检索：新查询进来时，按相关性打分取 top-k，注入后续上下文。

检索先用「关键词重叠打分」手写实现（先原理，不依赖向量库）；
接口上保留了以后替换成向量检索/LLM 提取的空间。
"""
import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Protocol

from pi_agent.types import Message, UserMessage


# ============ 记忆条目 ============

@dataclass
class Memory:
    """一条长期记忆：内容 + 来源 + 标签。"""
    id: str
    content: str
    source_session: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: int = 0


# ============ 存储 ============

class MemoryStore(Protocol):
    def add(self, memory: Memory) -> None: ...
    def all(self) -> list[Memory]: ...
    def clear(self) -> None: ...


class InMemoryMemoryStore:
    """内存版存储：进程内生效，用于测试或短生命周期。"""

    def __init__(self):
        self._items: dict[str, Memory] = {}

    def add(self, memory: Memory) -> None:
        self._items[memory.id] = memory

    def all(self) -> list[Memory]:
        return list(self._items.values())

    def clear(self) -> None:
        self._items.clear()


class JsonMemoryStore:
    """JSON 文件版存储：记忆落盘，跨会话/跨进程存活。"""

    def __init__(self, path: str):
        self._path = path
        self._items: dict[str, Memory] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for raw in data:
                mem = Memory(**raw)
                self._items[mem.id] = mem

    def _save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump([asdict(m) for m in self._items.values()], f, ensure_ascii=False, indent=2)

    def add(self, memory: Memory) -> None:
        self._items[memory.id] = memory
        self._save()

    def all(self) -> list[Memory]:
        return list(self._items.values())

    def clear(self) -> None:
        self._items.clear()
        self._save()


# ============ 提取 ============

def extract_memories(messages: list[Message], session_id: str = "") -> list[Memory]:
    """从会话消息里提取记忆（朴素版：取用户消息文本作为候选事实）。

    这是"手写原理"的第一步——先不依赖 LLM 做摘要，直接把用户说过的话
    当成要记住的事实；之后可把这里替换成 LLM 提炼（复用已有的 stream_fn）。
    """
    memories: list[Memory] = []
    for m in messages:
        if not isinstance(m, UserMessage):
            continue
        text = m.content if isinstance(m.content, str) else "".join(
            c.text for c in m.content if c.type == "text"
        )
        text = text.strip()
        if not text:
            continue
        memories.append(Memory(
            id=f"mem-{len(memories) + 1}-{m.timestamp}",
            content=text,
            source_session=session_id,
            tags=[],
            created_at=m.timestamp,
        ))
    return memories


# ============ 检索 ============

def _terms(text: str) -> set[str]:
    """把文本切成检索词项。

    - ASCII 词：按字母/数字/下划线切（英文有天然空格边界）。
    - 中文：没有空格，切成「字符二元组」（bigram），无需分词库即可手写。
    """
    terms: set[str] = set()
    terms.update(re.findall(r"[a-zA-Z0-9_]+", text.lower()))
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(run) == 1:
            terms.add(run)
        else:
            terms.update(run[i:i + 2] for i in range(len(run) - 1))
    return terms


def memory_score(memory: Memory, query: str) -> float:
    """词项重叠打分：查询词项被记忆覆盖的比例。"""
    q = _terms(query)
    if not q:
        return 0.0
    c = _terms(memory.content)
    return len(q & c) / len(q)


def retrieve(store: MemoryStore, query: str, k: int = 5) -> list[Memory]:
    """按相关性取 top-k 记忆。"""
    scored = [(memory_score(m, query), m) for m in store.all()]
    scored = [(s, m) for s, m in scored if s > 0]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [m for _, m in scored[:k]]
