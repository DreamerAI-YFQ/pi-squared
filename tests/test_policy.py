"""M2 治理测试：路径守卫 + 审批协议 + 钩子接入。"""
import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pi_agent.server.app import create_app
from pi_agent.server.policy import ApprovalManager, PathGuard, PolicyConfig, make_hooks


class FakeToolCall:
    """最小 tool_call 替身（钩子只用到 name/arguments）。"""

    def __init__(self, name: str, arguments: dict):
        self.name = name
        self.arguments = arguments


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


# ============ 路径守卫 ============


def test_path_guard_allows_inside(workspace):
    assert PathGuard(workspace).check("a.txt") is None
    assert PathGuard(workspace).check("sub/dir/file.py") is None
    assert PathGuard(workspace).check(str(workspace / "x.txt")) is None


def test_path_guard_blocks_escape(workspace, tmp_path):
    guard = PathGuard(workspace)
    # 绝对路径指向工作区外
    assert guard.check(str(tmp_path / "outside.txt")) is not None
    # 相对路径 .. 逃逸
    assert guard.check("../secret.txt") is not None
    assert guard.check("sub/../../escape.txt") is not None


# ============ 审批协议 ============


def test_approval_manager_protocol(workspace, tmp_path):
    """核心协议：request 挂起 → 事件入队列 → resolve → 返回结果。"""
    audit_log: list[dict] = tmp_path / "audit.jsonl"
    emitted: list[dict] = []
    pending: dict[str, list] = {}

    async def emit(event: dict):
        emitted.append(event)
        pending.setdefault(event.get("approvalId", ""), []).append(event)

    def audit(kind: str, **record):
        with open(audit_log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": kind, **record}) + "\n")

    async def scenario():
        mgr = ApprovalManager(emit=emit, audit=audit)
        task = asyncio.create_task(mgr.request("write", {"path": "a.txt", "content": "x"}))
        # 等待审批请求事件到达
        await asyncio.sleep(0.05)
        assert mgr.has_pending
        request_events = [e for e in emitted if e["type"] == "approval_request"]
        assert len(request_events) == 1
        approval_id = request_events[0]["approvalId"]

        # 批准
        assert mgr.resolve(approval_id, True)
        approved, reason = await task
        assert approved
        assert "批准" in reason
        assert not mgr.has_pending

        # 重复 resolve 应失败（已处理）
        assert not mgr.resolve(approval_id, True)

        # 拒绝路径
        task2 = asyncio.create_task(mgr.request("bash", {"command": "rm -rf /"}))
        await asyncio.sleep(0.05)
        request2 = [e for e in emitted if e["type"] == "approval_request"][-1]
        assert mgr.resolve(request2["approvalId"], False)
        approved2, reason2 = await task2
        assert not approved2

        # resolved 事件已发出
        resolved = [e for e in emitted if e["type"] == "approval_resolved"]
        assert len(resolved) == 2

    asyncio.run(scenario())

    # 审计包含请求与结果
    lines = [json.loads(l) for l in audit_log.read_text(encoding="utf-8").splitlines()]
    kinds = [l["kind"] for l in lines]
    assert "approval_request" in kinds
    assert "approval_result" in kinds


# ============ 钩子接入 ============


def _make_runtime_parts(workspace: Path, tmp_path: Path, auto_approve: set[str]):
    emitted: list[dict] = []
    audit_path = tmp_path / "audit.jsonl"

    async def emit(event: dict):
        emitted.append(event)

    def audit(kind: str, **record):
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": kind, **record}, ensure_ascii=False) + "\n")

    mgr = ApprovalManager(emit=emit, audit=audit)
    before, after = make_hooks(workspace=workspace, approvals=mgr, auto_approve=auto_approve)
    return before, after, mgr, emitted, audit_path


def test_hook_read_in_auto_approve_passes(workspace, tmp_path):
    """read 免审批 + 路径合法 → 直接放行（无审批事件）。"""
    before, after, mgr, emitted, _ = _make_runtime_parts(workspace, tmp_path, {"read"})

    async def scenario():
        result = await before(FakeToolCall("read", {"path": "a.txt"}), {"path": "a.txt"})
        assert result is None

    asyncio.run(scenario())
    assert emitted == []


def test_hook_write_requires_approval(workspace, tmp_path):
    """write 不在免审批列表 → 触发审批 → 拒绝则 block。"""
    before, _, mgr, emitted, _ = _make_runtime_parts(workspace, tmp_path, {"read"})

    async def scenario():
        task = asyncio.create_task(before(FakeToolCall("write", {"path": "a.txt"}), {"path": "a.txt"}))
        await asyncio.sleep(0.05)
        request = [e for e in emitted if e["type"] == "approval_request"][0]
        mgr.resolve(request["approvalId"], False)
        result = await task
        assert result is not None
        assert result.get("block") is True
        assert "未获批准" in result["reason"]

    asyncio.run(scenario())


def test_hook_blocks_path_escape_before_approval(workspace, tmp_path):
    """越界路径直接 block，不进入审批流程。"""
    before, _, mgr, emitted, _ = _make_runtime_parts(workspace, tmp_path, set())

    async def scenario():
        result = await before(FakeToolCall("write", {"path": "../x.txt"}), {"path": "../x.txt"})
        assert result is not None
        assert "越界" in result["reason"]
        # 未产生审批事件
        assert [e for e in emitted if e["type"] == "approval_request"] == []

    asyncio.run(scenario())


# ============ API 集成 ============


def test_policy_api_roundtrip(tmp_path: Path):
    data_dir = tmp_path / "data"
    workspace_root = tmp_path / "ws"
    data_dir.mkdir()
    workspace_root.mkdir()
    client = TestClient(create_app(data_dir, workspace_root, provider="faux"))

    resp = client.get("/api/policy")
    assert resp.status_code == 200
    assert "read" in resp.json()["autoApprove"]

    resp = client.put("/api/policy", json={"autoApprove": ["read", "bash"]})
    assert resp.status_code == 200
    assert set(resp.json()["autoApprove"]) == {"read", "bash"}

    # 持久化验证
    config = json.loads((data_dir / "config.json").read_text(encoding="utf-8"))
    assert set(config["autoApprove"]) == {"read", "bash"}


def test_approval_route_validation(tmp_path: Path):
    """审批路由：不存在的会话 404，无效审批 id 410。"""
    data_dir = tmp_path / "data"
    workspace_root = tmp_path / "ws"
    data_dir.mkdir()
    workspace_root.mkdir()
    client = TestClient(create_app(data_dir, workspace_root, provider="faux"))

    session_id = client.post("/api/sessions").json()["id"]
    resp = client.post(f"/api/sessions/{session_id}/approvals/xxxx", json={"approved": True})
    assert resp.status_code == 410
    resp = client.post("/api/sessions/nope/approvals/xxxx", json={"approved": True})
    assert resp.status_code == 404


def test_faux_flow_still_works_with_governance(tmp_path: Path):
    """M1 的 faux 流程在治理接入后仍正常（read 免审批，相对路径合法）。"""
    data_dir = tmp_path / "data"
    workspace_root = tmp_path / "ws"
    data_dir.mkdir()
    workspace_root.mkdir()
    client = TestClient(create_app(data_dir, workspace_root, provider="faux"))

    session_id = client.post("/api/sessions").json()["id"]
    with client.stream(
        "POST", f"/api/sessions/{session_id}/messages", json={"text": "读取 a.txt"}
    ) as resp:
        text = "".join(resp.iter_text())

    # 不应出现审批请求（read 免审批）
    assert "approval_request" not in text
    assert "tool_execution_end" in text
    # 审计已落盘：read 的 tool_result
    audit = (data_dir / "sessions" / session_id / "audit.jsonl").read_text(encoding="utf-8")
    assert "tool_result" in audit
