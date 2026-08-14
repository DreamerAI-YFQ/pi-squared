import asyncio

from pi_agent.harness.session.memory import InMemorySessionRepo
from pi_agent.harness.session.session import Session
from pi_agent.types import UserMessage


def test_session_append_and_query():
    repo = InMemorySessionRepo()
    storage = asyncio.run(repo.create())
    session = Session(storage)

    entry_id = asyncio.run(session.append_message(UserMessage(content="hi", timestamp=0)))

    entries = asyncio.run(session.find_entries())
    assert len(entries) == 1
    assert entries[0].id == entry_id
    assert entries[0].seq == 1


def test_repo_open_and_list():
    repo = InMemorySessionRepo()
    storage = asyncio.run(repo.create(session_id="s1"))
    opened = asyncio.run(repo.open("s1"))
    assert opened is storage
    assert asyncio.run(repo.list()) == ["s1"]


def test_multiple_entries_seq_increment():
    repo = InMemorySessionRepo()
    session = Session(asyncio.run(repo.create()))

    asyncio.run(session.append_message(UserMessage(content="a", timestamp=0)))
    asyncio.run(session.append_message(UserMessage(content="b", timestamp=0)))

    entries = asyncio.run(session.find_entries())
    # 默认 newestFirst（最新在前），所以用排序验证 seq 集合正确
    assert sorted(e.seq for e in entries) == [1, 2]
