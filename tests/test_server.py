"""网关测试：REST + SSE（faux provider，无需 API key）。"""
import json
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
    # provider 强制 faux：测试不依赖 .env 里的 key，也不产生真实 API 花费
    app = create_app(data_dir, workspace_root, provider="faux")
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


def test_messages_survive_restart(tmp_path: Path):
    """回归：重启服务后历史消息不丢失。

    历史 bug：SessionRuntime 每次构造都调用 JsonlSessionStorage.create，
    用 "w" 覆盖 session.jsonl，导致重启后消息被清掉只剩 header。
    """
    data_dir = tmp_path / "data"
    ws_root = tmp_path / "ws"
    data_dir.mkdir()
    ws_root.mkdir()

    # 第一次"启动"：创建会话并发消息
    app1 = create_app(data_dir, ws_root, provider="faux")
    with TestClient(app1) as c1:
        sid = c1.post("/api/sessions").json()["id"]
        with c1.stream("POST", f"/api/sessions/{sid}/messages", json={"text": "你好"}) as resp:
            list(resp.iter_text())
        # 磁盘文件应包含消息条目（不仅仅是 header）
        import json as _json
        jsonl = data_dir / "sessions" / sid / "session.jsonl"
        lines = [l for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
        kinds = [_json.loads(l).get("kind") for l in lines]
        assert "entry" in kinds, f"消息未落盘，只有：{kinds}"

    # 模拟重启：用同一份 data_dir 创建全新的 app/registry（_runtimes 为空）
    app2 = create_app(data_dir, ws_root, provider="faux")
    with TestClient(app2) as c2:
        # 列表仍能看到会话
        ids = [s["id"] for s in c2.get("/api/sessions").json()]
        assert sid in ids
        # 会话详情能读出消息（user + assistant + toolResult）
        resp = c2.get(f"/api/sessions/{sid}")
        assert resp.status_code == 200
        messages = resp.json()["messages"]
        roles = [m["role"] for m in messages]
        assert "user" in roles, f"重启后 user 消息丢失：{roles}"
        assert "assistant" in roles
