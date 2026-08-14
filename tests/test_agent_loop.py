import asyncio

from pydantic import BaseModel

from pi_agent.agent_loop import AgentLoopConfig, run_agent_loop
from pi_agent.providers.faux import faux_stream
from pi_agent.types import AgentContext, AgentTool, AgentToolResult, TextContent, UserMessage


class ReadParams(BaseModel):
    path: str


async def read(tool_call_id: str, params: dict) -> AgentToolResult:
    return AgentToolResult(content=[TextContent(text=f"内容: {params['path']}")], details={})


def test_react_loop():
    tool = AgentTool(name="read", description="读取文件", parameters=ReadParams, execute=read)
    context = AgentContext(systemPrompt="", messages=[], tools=[tool])
    config = AgentLoopConfig(stream_fn=faux_stream)

    events = []

    async def emit(event):
        events.append(event)

    messages = asyncio.run(
        run_agent_loop(
            prompts=[UserMessage(content="读 a.txt", timestamp=0)],
            context=context,
            config=config,
            emit=emit,
        )
    )

    # 事件序列里应包含工具执行，且以 agent_end 收尾
    event_types = [e.type for e in events]
    assert "tool_execution_start" in event_types
    assert "tool_execution_end" in event_types
    assert event_types[-1] == "agent_end"

    # 消息序列：user -> assistant(含 toolCall) -> toolResult -> assistant(最终回答)
    assert [m.role for m in messages] == ["user", "assistant", "toolResult", "assistant"]
    assert messages[-1].content[0].text == "已完成读取"
