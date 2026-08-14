import asyncio

from pi_agent.harness.session.context import build_session_context
from pi_agent.harness.session.session import Session
from pi_agent.harness.session.storage import JsonlSessionStorage
from pi_agent.types import UserMessage


def test_jsonl_persist_and_replay(tmp_path):
    path = str(tmp_path / "session.jsonl")

    # 创建 + 追加消息
    storage = JsonlSessionStorage.create(path, session_id="s1")
    session = Session(storage)
    asyncio.run(session.append_message(UserMessage(content="hi", timestamp=0)))
    asyncio.run(session.append_message(UserMessage(content="there", timestamp=0)))

    # 重新打开（重放）
    reopened = JsonlSessionStorage.open(path)
    entries = asyncio.run(reopened.find_entries())
    # find_entries 默认 newestFirst（倒序）；还原上下文需要 oldestFirst（正序）
    entries_sorted = sorted(entries, key=lambda e: e.seq)
    messages = build_session_context(entries_sorted)
    assert [m.content for m in messages] == ["hi", "there"]


def test_jsonl_metadata_roundtrip(tmp_path):
    path = str(tmp_path / "s.jsonl")
    storage = JsonlSessionStorage.create(path, session_id="abc")
    reopened = JsonlSessionStorage.open(path)
    meta = asyncio.run(reopened.get_metadata())
    assert meta.id == "abc"
