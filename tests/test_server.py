"""网关测试：REST + SSE（faux provider，无需 API key）。"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pi_agent.server.app import create_app


@pytest.fixture()
def client(tmp_path: Path):
    data_dir = tmp_path / "data"
    workspace_root = tmp_path / "workspaces"
    data_dir.mkdir()
    workspace_root.mkdir()
    app = create_app(data_dir, workspace_root)
    return TestClient(app)


def _parse_sse(text: str) -> list[dict]:
    """从 SSE 文本中解析出所有事件。"""
    events = []
    for frame in text.split("\n\n"):
        for line in frame.split("\n"):
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


def test_config(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Pi²"
    assert data["provider"] in ("faux", "deepseek")


def test_create_and_list_session(client):
    resp = client.post("/api/sessions")
    assert resp.status_code == 200
    session_id = resp.json()["id"]

    resp = client.get("/api/sessions")
    ids = [s["id"] for s in resp.json()]
    assert session_id in ids


def test_send_message_sse(client):
    session_id = client.post("/api/sessions").json()["id"]

    with client.stream(
        "POST", f"/api/sessions/{session_id}/messages", json={"text": "读取 a.txt"}
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        text = "".join(resp.iter_text())

    events = _parse_sse(text)
    types = [e["type"] for e in events]

    # faux provider：agent → turn → user/assistant/tool 消息 → agent_end
    assert types[0] == "agent_start"
    assert types[-1] == "agent_end"
    assert "tool_execution_start" in types
    assert "tool_execution_end" in types
    assert "message_end" in types


def test_session_restore(client):
    """发消息后重新 GET 会话，应能从 JSONL 恢复历史。"""
    session_id = client.post("/api/sessions").json()["id"]

    with client.stream(
        "POST", f"/api/sessions/{session_id}/messages", json={"text": "读取 a.txt"}
    ) as resp:
        list(resp.iter_text())

    resp = client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    roles = [m["role"] for m in messages]
    assert "user" in roles
    assert "assistant" in roles
    assert "toolResult" in roles


def test_unknown_session_404(client):
    assert client.get("/api/sessions/nope").status_code == 404
