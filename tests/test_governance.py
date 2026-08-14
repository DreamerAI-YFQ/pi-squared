import asyncio

from pi_agent.harness.governance import Governance
from pi_agent.types import ToolCall


def _call(name: str) -> ToolCall:
    return ToolCall(id="c1", name=name, arguments={})


def test_denylist_blocks():
    gov = Governance(denylist=["bash"])
    result = asyncio.run(gov.before_tool_call(_call("bash"), {}))
    assert result is not None
    assert result["block"] is True


def test_allowlist_blocks_unknown():
    gov = Governance(allowlist=["read", "write"])
    result = asyncio.run(gov.before_tool_call(_call("bash"), {}))
    assert result is not None
    assert result["block"] is True


def test_no_restriction_allows():
    gov = Governance()
    result = asyncio.run(gov.before_tool_call(_call("bash"), {}))
    assert result is None


def test_audit_writes(tmp_path):
    path = str(tmp_path / "audit.jsonl")
    gov = Governance(audit_path=path)
    asyncio.run(gov.after_tool_call(_call("read"), None, False))

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1
    assert '"read"' in lines[0]
