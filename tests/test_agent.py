import asyncio

from pydantic import BaseModel

from pi_agent.agent import Agent
from pi_agent.providers.faux import faux_stream
from pi_agent.types import AgentTool, AgentToolResult, TextContent


class ReadParams(BaseModel):
    path: str


async def read(tool_call_id: str, params: dict) -> AgentToolResult:
    return AgentToolResult(content=[TextContent(text=f"内容: {params['path']}")], details={})


def test_agent_prompt():
    tool = AgentTool(name="read", description="读取文件", parameters=ReadParams, execute=read)
    agent = Agent(stream_fn=faux_stream, tools=[tool])
    events = []
    agent.subscribe(lambda e: events.append(e))

    asyncio.run(agent.prompt("读 a.txt"))

    # 对话历史：user -> assistant(含 toolCall) -> toolResult -> assistant(最终回答)
    assert [m.role for m in agent.messages] == ["user", "assistant", "toolResult", "assistant"]
    assert agent.messages[-1].content[0].text == "已完成读取"

    # 事件序列以 agent_start 开头、agent_end 收尾
    assert events[0].type == "agent_start"
    assert events[-1].type == "agent_end"


def test_agent_subscribe_unsubscribe():
    agent = Agent(stream_fn=faux_stream, tools=[])
    seen = []

    def listener(event):
        seen.append(event.type)

    unsubscribe = agent.subscribe(listener)
    asyncio.run(agent.prompt("hello"))
    assert "agent_end" in seen

    unsubscribe()
    seen.clear()
    asyncio.run(agent.prompt("again"))
    assert seen == []
