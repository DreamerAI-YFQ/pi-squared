from pi_agent.harness.search import search_entries
from pi_agent.harness.session.types import MessageEntry
from pi_agent.types import TextContent, UserMessage


def _msg(entry_id: str, seq: int, text: str) -> MessageEntry:
    return MessageEntry(message=UserMessage(content=text, timestamp=0), id=entry_id, seq=seq)


def test_search_finds_matches():
    entries = [
        _msg("e1", 1, "读取 a.txt 文件"),
        _msg("e2", 2, "修改 b.txt 文件"),
    ]
    results = search_entries(entries, "a.txt")
    assert [e.id for e in results] == ["e1"]


def test_search_case_insensitive():
    entries = [_msg("e1", 1, "Hello World")]
    assert len(search_entries(entries, "hello")) == 1


def test_search_no_match():
    entries = [_msg("e1", 1, "读取文件")]
    assert search_entries(entries, "不存在") == []
