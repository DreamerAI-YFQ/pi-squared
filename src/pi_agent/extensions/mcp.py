"""MCP 客户端（对应 ETCLOVG 的 T 层，特色实现）。

MCP（Model Context Protocol）用 JSON-RPC 2.0 让 agent 发现并调用外部工具服务。
这里手写最小客户端，走通协议核心：initialize -> tools/list -> tools/call，
再把 MCP 工具包装成 agent_loop 认识的 AgentTool。

传输层抽象成 Transport（send/receive），默认提供 stdio 版（子进程 stdin/stdout，
一行一个 JSON）；测试可注入内存版 transport，离线验证协议。
"""
import asyncio
import json
from typing import Any, Optional, Protocol

from pydantic import BaseModel, create_model

from pi_agent.types import AgentTool, AgentToolResult, TextContent


class MCPError(Exception):
    """MCP 协议错误。"""


# ============ 传输层 ============

class Transport(Protocol):
    async def send(self, message: dict) -> None: ...
    async def receive(self) -> dict: ...


class StdioTransport:
    """stdio 传输：spawn 子进程，stdin/stdout 走「换行分隔 JSON」。"""

    def __init__(self, command: list[str]):
        self._command = command
        self._proc: asyncio.subprocess.Process | None = None

    async def __aenter__(self) -> "StdioTransport":
        self._proc = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._proc and self._proc.stdin:
            self._proc.stdin.close()
        if self._proc:
            await self._proc.wait()

    async def send(self, message: dict) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write((json.dumps(message) + "\n").encode())
        await self._proc.stdin.drain()

    async def receive(self) -> dict:
        assert self._proc and self._proc.stdout
        line = await self._proc.stdout.readline()
        if not line:
            raise MCPError("MCP 服务进程已关闭")
        return json.loads(line)


# ============ JSON-RPC 客户端 ============

class MCPClient:
    """最小 JSON-RPC 客户端（只做请求-响应，忽略通知）。"""

    def __init__(self, transport: Transport):
        self._transport = transport
        self._next_id = 0

    async def _request(self, method: str, params: dict | None = None) -> Any:
        req_id = self._next_id
        self._next_id += 1
        await self._transport.send({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        })
        while True:
            resp = await self._transport.receive()
            if resp.get("id") == req_id:
                if "error" in resp:
                    err = resp["error"]
                    raise MCPError(f"{err.get('code')}: {err.get('message')}")
                return resp.get("result")
            # 最小实现：忽略非本请求 id 的消息（通知等）

    async def initialize(self) -> dict:
        """握手，返回服务端能力。"""
        return await self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pi-agent", "version": "0.1.0"},
        })

    async def list_tools(self) -> list[dict]:
        """获取服务端工具定义列表。"""
        result = await self._request("tools/list")
        return result.get("tools", [])

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """调用一个 MCP 工具，返回原始 result（含 content/isError）。"""
        return await self._request("tools/call", {"name": name, "arguments": arguments})


# ============ JSON Schema -> pydantic ============

def _py_type(json_type: str | None) -> Any:
    mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return mapping.get(json_type, Any)


def json_schema_to_pydantic(schema: dict, name: str = "MCPParams") -> type[BaseModel]:
    """把 MCP 工具的 inputSchema（JSON Schema）转成 pydantic 模型。

    只处理基础类型（string/integer/number/boolean/array/object），
    覆盖绝大多数 MCP 工具参数；这正好呼应 T 层的「工具 schema 标准化」。
    """
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    field_defs: dict[str, Any] = {}
    for key, prop in props.items():
        t = _py_type(prop.get("type"))
        if key in required:
            field_defs[key] = (t, ...)
        else:
            field_defs[key] = (Optional[t], None)
    return create_model(name, **field_defs)


# ============ MCP 工具 -> AgentTool ============

def mcp_tool_to_agent_tool(client: MCPClient, tool_def: dict) -> AgentTool:
    """把一个 MCP 工具定义包装成 AgentTool（agent_loop 可直接调用）。"""
    name = tool_def["name"]
    description = tool_def.get("description", "")
    params_model = json_schema_to_pydantic(
        tool_def.get("inputSchema", {}),
        name=f"{name.replace('-', '_').replace('.', '_').title()}Params",
    )

    async def execute(tool_call_id: str, params: dict) -> AgentToolResult:
        result = await client.call_tool(name, params)
        texts = [
            item.get("text", "")
            for item in result.get("content", [])
            if item.get("type") == "text"
        ]
        text = "\n".join(texts)
        if result.get("isError"):
            # 语义失败：抛异常让 agent_loop 捕获并标记 is_error=True
            raise RuntimeError(text or "MCP 工具调用失败")
        return AgentToolResult(content=[TextContent(text=text)])

    return AgentTool(
        name=name,
        description=description,
        parameters=params_model,
        execute=execute,
    )


async def wrap_mcp_tools(client: MCPClient) -> list[AgentTool]:
    """发现并包装服务端全部工具。"""
    tools = await client.list_tools()
    return [mcp_tool_to_agent_tool(client, t) for t in tools]
