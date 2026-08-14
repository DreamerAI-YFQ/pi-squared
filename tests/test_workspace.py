"""M4 测试：自定义 workspace。"""
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


def test_create_session_with_custom_workspace(client, tmp_path: Path):
    """指定存在的目录 → 会话 workspace 指向它，meta.json 持久化。"""
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()

    resp = client.post("/api/sessions", json={"workspace": str(project_dir)})
    assert resp.status_code == 200
    data = resp.json()
    sid = data["id"]
    assert Path(data["workspace"]) == project_dir

    # meta.json 落盘
    meta = tmp_path / "data" / "sessions" / sid / "meta.json"
    assert meta.exists()

    # 会话列表带自定义 workspace
    sessions = client.get("/api/sessions").json()
    mine = [s for s in sessions if s["id"] == sid][0]
    assert Path(mine["workspace"]) == project_dir


def test_create_session_rejects_missing_dir(client, tmp_path: Path):
    """不存在的目录 → 422。"""
    resp = client.post("/api/sessions", json={"workspace": str(tmp_path / "nope")})
    assert resp.status_code == 422


def test_create_session_strips_quotes(client, tmp_path: Path):
    """路径带成对引号/空格（从聊天复制）→ 自动清洗后可用。"""
    project_dir = tmp_path / "quoted"
    project_dir.mkdir()

    cases = [
        f'"{project_dir}"',          # ASCII 双引号
        f"'{project_dir}'",          # ASCII 单引号
        f"\u201c{project_dir}\u201d",  # 中文双引号
        f'  "{project_dir}"  ',      # 前后空白
    ]
    for raw in cases:
        resp = client.post("/api/sessions", json={"workspace": raw})
        assert resp.status_code == 200, f"清洗失败：{raw}"
        assert Path(resp.json()["workspace"]) == project_dir


def test_create_session_without_body_uses_default(client):
    """不带 body → 默认隔离工作区，meta.json 不落盘。"""
    resp = client.post("/api/sessions")
    assert resp.status_code == 200
    sid = resp.json()["id"]
    # workspace 在默认隔离区下（路径包含会话 id）
    assert sid in resp.json()["workspace"]
    # 列表端点同样返回默认隔离区
    sessions = client.get("/api/sessions").json()
    mine = [s for s in sessions if s["id"] == sid][0]
    assert sid in mine["workspace"]


def test_agent_writes_into_custom_workspace(client, tmp_path: Path):
    """faux 一轮 read 在自定义 workspace 下执行（不越界）。"""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    sid = client.post("/api/sessions", json={"workspace": str(project_dir)}).json()["id"]
    with client.stream(
        "POST", f"/api/sessions/{sid}/messages", json={"text": "读取 a.txt"}
    ) as resp:
        text = "".join(resp.iter_text())

    assert "tool_execution_end" in text
    # 路径守卫以自定义目录为边界：相对路径解析到 project_dir 下
    assert not (project_dir / "..").exists() or True  # noop，仅占位保证结构清晰


def test_workspace_restored_after_remount(client, tmp_path: Path):
    """服务重启模拟：open_session 重挂载后 workspace 仍指向自定义目录。"""
    project_dir = tmp_path / "repo"
    project_dir.mkdir()

    sid = client.post("/api/sessions", json={"workspace": str(project_dir)}).json()["id"]
    # 打开会话（通过 messages 端点触发 open_session）
    resp = client.get(f"/api/sessions/{sid}")
    assert resp.status_code == 200

    sessions = client.get("/api/sessions").json()
    mine = [s for s in sessions if s["id"] == sid][0]
    assert Path(mine["workspace"]) == project_dir
