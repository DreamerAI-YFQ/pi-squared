"""会话搜索（对应 pi 的 search/scanning.ts 简化版）。

全量扫描式全文搜索：在会话 entries 的 message 内容里匹配 query。
"""
from pi_agent.harness.session.types import Entry
from pi_agent.types import Message


def _content_to_text(message: Message) -> str:
    if isinstance(message.content, str):
        return message.content
    parts = []
    for block in message.content:
        if block.type == "text":
            parts.append(block.text)
        elif block.type == "toolCall":
            parts.append(block.name)
    return "".join(parts)


def search_entries(entries: list[Entry], query: str) -> list[Entry]:
    """全文搜索：在 message entry 的内容里匹配 query（大小写不敏感）。"""
    query_lower = query.lower()
    results: list[Entry] = []
    for entry in entries:
        if entry.type != "message":
            continue
        text = _content_to_text(entry.message)
        if query_lower in text.lower():
            results.append(entry)
    return results
