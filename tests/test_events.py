from pi_agent.events import AgentEnd, ToolExecutionEnd
from pi_agent.types import AgentToolResult, TextContent


def test_agent_end_event():
    event = AgentEnd(messages=[])
    assert event.type == "agent_end" #assert是断言语句，用于检查事件类型是否符合预期
    assert event.messages == [] # 检查事件消息是否为空


def test_tool_execution_end_event():
    result = AgentToolResult(content=[TextContent(text="ok")], details={})
    event = ToolExecutionEnd(toolCallId="1", toolName="read", result=result, isError=False)
    assert event.type == "tool_execution_end"
    assert event.toolName == "read"
    assert event.result.content[0].text == "ok"
