"""M3 观测面板测试：span 树 + 指标 + 落盘。"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pi_agent.server.app import create_app


@pytest.fixture()
def client(tmp_path: Path):
    data_dir = tmp_path / "data"
    workspace_root = tmp_path / "ws"
    data_dir.mkdir()
    workspace_root.mkdir()
    app = create_app(data_dir, workspace_root, provider="faux")
    return TestClient(app)


def test_observability_empty_snapshot(client):
    session_id = client.post("/api/sessions").json()["id"]
    resp = client.get(f"/api/sessions/{session_id}/observability")
    assert resp.status_code == 200
    data = resp.json()
    assert data["spans"] == []
    assert data["totalTokens"] == 0
    assert data["model"] == "faux"


def test_observability_after_prompt(client, tmp_path: Path):
    """faux 一轮：span 树结构 agent_prompt > turn > tool:read，trace.json 落盘。"""
    data_dir = tmp_path / "data"
    session_id = client.post("/api/sessions").json()["id"]
    with client.stream(
        "POST", f"/api/sessions/{session_id}/messages", json={"text": "读取 a.txt"}
    ) as resp:
        assert resp.status_code == 200
        _ = "".join(resp.iter_text())

    resp = client.get(f"/api/sessions/{session_id}/observability")
    assert resp.status_code == 200
    data = resp.json()

    # span 树：root = agent_prompt，其下至少一个 turn，turn 下有 tool:read
    spans = data["spans"]
    assert len(spans) >= 1
    root = spans[0]
    assert root["name"] == "agent_prompt"
    assert root["children"], "agent_prompt 下应有 turn span"
    turn = root["children"][0]
    assert turn["name"] == "turn"
    tool_spans = [c for c in turn["children"] if c["name"].startswith("tool:")]
    assert tool_spans, "turn 下应有 tool span"
    assert tool_spans[0]["name"] == "tool:read"
    assert "duration_ms" in tool_spans[0]

    # 工具调用计数
    assert data["toolCalls"] >= 1

    # trace.json 已落盘
    trace_file = data_dir / "sessions" / session_id / "trace.json"
    assert trace_file.exists()
    import json as _json

    trace = _json.loads(trace_file.read_text(encoding="utf-8"))
    assert trace["spans"], "落盘的 trace 应含 span 树"


def test_observability_404(client):
    resp = client.get("/api/sessions/nope/observability")
    assert resp.status_code == 404
