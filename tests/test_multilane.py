import asyncio

from pi_agent.harness.session.memory import InMemorySessionStorage
from pi_agent.harness.session.session import Session
from pi_agent.harness.session.storage import JsonlSessionStorage
from pi_agent.harness.session.types import MessageEntry, SessionMetadata
from pi_agent.types import UserMessage


def run(coro):
    return asyncio.run(coro)


def test_memory_multiple_lanes():
    async def main():
        storage = InMemorySessionStorage(SessionMetadata(id="s", created_at=0))
        await storage.append_entry(MessageEntry(message=UserMessage(content="a", timestamp=1)), "main")
        main_leaf = (await storage.find_lanes())["main"]

        await storage.create_lane("branch", leaf_id=main_leaf)
        await storage.append_entry(MessageEntry(message=UserMessage(content="b", timestamp=2)), "branch")

        lanes = await storage.find_lanes()
        assert lanes["main"] == main_leaf
        assert lanes["branch"] is not None
        assert lanes["branch"] != main_leaf

    run(main())


def test_session_append_message_to_lane():
    async def main():
        session = Session(InMemorySessionStorage(SessionMetadata(id="s", created_at=0)))
        await session.append_message(UserMessage(content="a", timestamp=1))
        leaf = (await session.find_lanes())["main"]

        await session.create_lane("branch", leaf_id=leaf)
        await session.append_message(UserMessage(content="b", timestamp=2), lane="branch")

        assert "branch" in await session.find_lanes()

    run(main())


def test_jsonl_lane_persists(tmp_path):
    async def main():
        path = tmp_path / "s.jsonl"
        storage = JsonlSessionStorage.create(str(path))
        await storage.append_entry(MessageEntry(message=UserMessage(content="a", timestamp=1)), "main")
        leaf = (await storage.find_lanes())["main"]

        await storage.create_lane("branch", leaf_id=leaf)
        await storage.append_entry(MessageEntry(message=UserMessage(content="b", timestamp=2)), "branch")

        reopened = JsonlSessionStorage.open(str(path))
        lanes = await reopened.find_lanes()
        assert "branch" in lanes
        assert lanes["main"] == leaf

    run(main())
