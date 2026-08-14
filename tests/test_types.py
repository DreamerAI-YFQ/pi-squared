import asyncio # 异步库

from pydantic import BaseModel # 模型类，用于定义数据结构

from pi_agent.types import AgentContext, AgentTool, AgentToolResult, TextContent
# 导入 types.py 中的类型定义

class ReadParams(BaseModel):  # 读取文件参数模型
    path: str

# 模拟读取文件函数，返回固定内容
async def fake_read(tool_call_id: str, params: dict) -> AgentToolResult:
    return AgentToolResult(content=[TextContent(text="file content")], details={})

# 测试工具执行
def test_tool_execute():
    tool = AgentTool(name="read", description="读取文件", parameters=ReadParams, execute=fake_read)
    ctx = AgentContext(systemPrompt="", messages=[], tools=[tool])
    result = asyncio.run(tool.execute("id1", {"path": "a.txt"}))
    assert result.content[0].text == "file content"
    assert len(ctx.tools) == 1
