import asyncio
import sys

from pi_agent.extensions.mcp import (
    MCPClient,
    StdioTransport,
    json_schema_to_pydantic,
    mcp_tool_to_agent_tool,
    wrap_mcp_tools,
)


SAMPLE_TOOLS = [
    {
        "name": "add",
        "description": "两数相加",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
    }
]


class FakeMCPTransport:
    """内存版 transport：把 client 的 send 就地处理成响应，离线验证 JSON-RPC 协议。"""

    def __init__(self, tools=None, call_handler=None):
        self._tools = tools or []
        self._call_handler = call_handler or (lambda name, args: {"content": [{"type": "text", "text": f"called {name}"}]})
        self._outgoing = asyncio.Queue()

    async def send(self, message):
        resp = self._handle(message)
        await self._outgoing.put(resp)

    async def receive(self):
        return await self._outgoing.get()

    def _handle(self, msg):
        method = msg["method"]
        mid = msg["id"]
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": mid, "result": {"tools": self._tools}}
        if method == "tools/call":
            name = msg["params"]["name"]
            args = msg["params"].get("arguments", {})
            return {"jsonrpc": "2.0", "id": mid, "result": self._call_handler(name, args)}
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}}


def test_initialize():
    client = MCPClient(FakeMCPTransport())
    result = asyncio.run(client.initialize())
    assert result["protocolVersion"] == "2024-11-05"


def test_list_tools():
    client = MCPClient(FakeMCPTransport(tools=SAMPLE_TOOLS))
    tools = asyncio.run(client.list_tools())
    assert tools == SAMPLE_TOOLS


def test_call_tool():
    client = MCPClient(FakeMCPTransport())
    result = asyncio.run(client.call_tool("add", {"a": 1, "b": 2}))
    assert result["content"][0]["text"] == "called add"


def test_json_schema_to_pydantic():
    model = json_schema_to_pydantic(
        {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "string"}}, "required": ["a"]}
    )
    assert model(a=1, b="x").a == 1
    assert model(a=2).b is None


def test_mcp_tool_to_agent_tool():
    client = MCPClient(FakeMCPTransport(tools=SAMPLE_TOOLS))
    tool = mcp_tool_to_agent_tool(client, SAMPLE_TOOLS[0])
    result = asyncio.run(tool.execute("call-1", {"a": 1, "b": 2}))
    assert result.content[0].text == "called add"


def test_wrap_mcp_tools():
    client = MCPClient(FakeMCPTransport(tools=SAMPLE_TOOLS))
    tools = asyncio.run(wrap_mcp_tools(client))
    assert [t.name for t in tools] == ["add"]


def test_mcp_tool_error_raises():
    def handler(name, args):
        return {"content": [{"type": "text", "text": "boom"}], "isError": True}

    client = MCPClient(FakeMCPTransport(tools=SAMPLE_TOOLS, call_handler=handler))
    tool = mcp_tool_to_agent_tool(client, SAMPLE_TOOLS[0])
    try:
        asyncio.run(tool.execute("call-1", {"a": 1, "b": 2}))
        assert False, "应当抛出异常"
    except RuntimeError as e:
        assert "boom" in str(e)


SERVER_SRC = """\
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}}
    elif method == "tools/list":
        result = {"tools": [{"name": "echo", "description": "回显", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}]}
    elif method == "tools/call":
        text = msg["params"]["arguments"].get("text", "")
        result = {"content": [{"type": "text", "text": text}]}
    else:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "not found"}}) + "\\n")
        sys.stdout.flush()
        continue
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}) + "\\n")
    sys.stdout.flush()
"""


def test_stdio_transport(tmp_path):
    server = tmp_path / "mcp_server.py"
    server.write_text(SERVER_SRC, encoding="utf-8")

    async def main():
        async with StdioTransport([sys.executable, str(server)]) as transport:
            client = MCPClient(transport)
            await client.initialize()
            tools = await client.list_tools()
            assert tools[0]["name"] == "echo"
            result = await client.call_tool("echo", {"text": "hi"})
            assert result["content"][0]["text"] == "hi"

    asyncio.run(main())
