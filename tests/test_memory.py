from pi_agent.extensions.memory import (
    InMemoryMemoryStore,
    JsonMemoryStore,
    Memory,
    extract_memories,
    retrieve,
)
from pi_agent.types import UserMessage


def test_extract_memories_from_user_messages():
    messages = [
        UserMessage(content="我喜欢苹果", timestamp=1),
        UserMessage(content="项目使用 Python 3.11", timestamp=2),
    ]
    mems = extract_memories(messages, session_id="s1")

    assert len(mems) == 2
    assert mems[0].content == "我喜欢苹果"
    assert mems[0].source_session == "s1"
    assert mems[1].content == "项目使用 Python 3.11"


def test_retrieve_by_keyword():
    store = InMemoryMemoryStore()
    store.add(Memory(id="m1", content="用户喜欢苹果", created_at=1))
    store.add(Memory(id="m2", content="项目技术栈是 Python", created_at=2))
    store.add(Memory(id="m3", content="数据库用 PostgreSQL", created_at=3))

    results = retrieve(store, "项目 技术栈")
    assert results[0].id == "m2"


def test_json_store_persists_across_sessions(tmp_path):
    path = tmp_path / "memory.json"

    # 第一个"会话/进程"写入记忆
    store1 = JsonMemoryStore(str(path))
    store1.add(Memory(id="m1", content="用户偏好深色主题", created_at=1))

    # 第二个"会话/进程"重新打开同一文件，应能读到之前的记忆
    store2 = JsonMemoryStore(str(path))
    assert [m.content for m in store2.all()] == ["用户偏好深色主题"]
    assert retrieve(store2, "深色主题")[0].id == "m1"
