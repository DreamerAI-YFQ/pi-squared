"""FastAPI 网关：把 pi_agent 暴露为 REST + SSE。

路由一览：
    GET    /api/config                     provider 模式等信息
    POST   /api/sessions                   创建会话
    GET    /api/sessions                   会话列表（扫磁盘）
    GET    /api/sessions/{id}              恢复历史消息
    POST   /api/sessions/{id}/messages     发消息（SSE 流式响应）
    /                                  前端静态文件（web/dist）
"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from pi_agent.server.runtime import Registry

_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


class MessageBody(BaseModel):
    text: str


class ApprovalBody(BaseModel):
    approved: bool


class PolicyBody(BaseModel):
    autoApprove: list[str]


def create_app(data_dir: Path, workspace_root: Path, provider: str = "auto") -> FastAPI:
    app = FastAPI(title="Pi²", version="0.1.0")
    registry = Registry(data_dir, workspace_root, provider=provider)

    # 开发模式：Vite (5173) 访问后端 API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/config")
    async def config():
        return {
            "name": "Pi²",
            "version": "0.1.0",
            "provider": registry.provider_mode,
            "workspace_root": str(workspace_root),
        }

    @app.post("/api/sessions")
    async def create_session():
        runtime = registry.create_session()
        return {"id": runtime.id, "workspace": str(runtime.workspace)}

    @app.get("/api/sessions")
    async def list_sessions():
        return [
            {
                "id": s.id,
                "title": s.title,
                "createdAt": s.created_at,
                "updatedAt": s.updated_at,
                "workspace": s.workspace,
            }
            for s in registry.list_sessions()
        ]

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str):
        runtime = registry.open_session(session_id)
        if runtime is None:
            raise HTTPException(404, "会话不存在")
        messages = await runtime.load_messages()
        return {"id": session_id, "messages": messages}

    @app.get("/api/policy")
    async def get_policy():
        return {"autoApprove": sorted(registry.policy_config.auto_approve)}

    @app.put("/api/policy")
    async def put_policy(body: PolicyBody):
        """更新免审批工具列表（全局默认，持久化到 config.json）。"""
        registry.policy_config.auto_approve = set(body.autoApprove)
        registry.policy_config.save()
        return {"autoApprove": sorted(registry.policy_config.auto_approve)}

    @app.post("/api/sessions/{session_id}/approvals/{approval_id}")
    async def resolve_approval(session_id: str, approval_id: str, body: ApprovalBody):
        """前端响应审批：批准或拒绝挂起中的工具调用。"""
        runtime = registry.get(session_id)
        if runtime is None:
            raise HTTPException(404, "会话不存在")
        if not runtime.approvals.resolve(approval_id, body.approved):
            raise HTTPException(410, "审批请求不存在或已处理")

    @app.get("/api/sessions/{session_id}/observability")
    async def get_observability(session_id: str):
        """观测快照：span 树 + token/成本（O 层）。"""
        runtime = registry.open_session(session_id)
        if runtime is None:
            raise HTTPException(404, "会话不存在")
        return runtime.observability_snapshot()

    @app.post("/api/sessions/{session_id}/messages")
    async def send_message(session_id: str, body: MessageBody):
        runtime = registry.open_session(session_id)
        if runtime is None:
            raise HTTPException(404, "会话不存在")
        if runtime.busy:
            raise HTTPException(409, "会话正忙，请等待当前回合完成")
        return StreamingResponse(
            runtime.stream_events(body.text),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 前端静态托管：生产模式下 web/dist 由本服务直接提供
    if _DIST.exists():

        @app.get("/")
        async def index():
            return FileResponse(_DIST / "index.html")

        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=_DIST, html=True), name="web")

    return app
