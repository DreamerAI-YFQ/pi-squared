import asyncio

from pi_agent.agent import Agent
from pi_agent.harness.subagent import SubAgent
from pi_agent.types import AssistantMessage, TextContent, ToolCall


def test_subagent_run_returns_final_text():
    async def child_stream(context):
        return AssistantMessage(content=[TextContent(text="子任务完成")], stopReason="stop", timestamp=0)

    sub = SubAgent("researcher", "做研究", child_stream, "你是研究员")
    assert asyncio.run(sub.run("查资料")) == "子任务完成"


def test_subagent_as_tool():
    async def child_stream(context):
        return AssistantMessage(content=[TextContent(text="结果42")], stopReason="stop", timestamp=0)

    sub = SubAgent("calc", "计算", child_stream, "你是计算器")
    tool = sub.as_tool()

    result = asyncio.run(tool.execute("call-1", {"task": "算 1+1"}))
    assert result.content[0].text == "结果42"


def test_parent_calls_subagent():
    # 子智能体：返回固定调研结果
    async def child_stream(context):
        return AssistantMessage(content=[TextContent(text="深度调研结果：42")], stopReason="stop", timestamp=0)

    sub = SubAgent("researcher", "深度调研", child_stream, "研究员")

    # 父 Agent：第一轮调用 researcher 工具，第二轮给最终回答
    calls = 0

    async def parent_stream(context):
        nonlocal calls
        calls += 1
        if calls == 1:
            return AssistantMessage(
                content=[ToolCall(id="c1", name="researcher", arguments={"task": "调研"})],
                stopReason="toolUse",
                timestamp=0,
            )
        return AssistantMessage(content=[TextContent(text="调研完成")], stopReason="stop", timestamp=0)

    parent = Agent(stream_fn=parent_stream, tools=[sub.as_tool()])
    asyncio.run(parent.prompt("帮我调研"))

    tool_results = [m for m in parent.messages if m.role == "toolResult"]
    assert len(tool_results) == 1
    text = "".join(c.text for c in tool_results[0].content if c.type == "text")
    assert "深度调研结果：42" in text
