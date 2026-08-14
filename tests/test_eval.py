import asyncio

from pydantic import BaseModel

from pi_agent.extensions.eval import (
    EvalRunner,
    EvalTask,
    final_answer_contains,
    no_tool_errors,
    to_regression_case,
    tool_was_called,
    tool_was_called_with,
)
from pi_agent.types import AgentTool, AgentToolResult, AssistantMessage, TextContent, ToolCall


class ReadParams(BaseModel):
    path: str


async def read_execute(tool_call_id: str, params: dict) -> AgentToolResult:
    return AgentToolResult(content=[TextContent(text=f"read {params['path']}")])


read_tool = AgentTool(
    name="read",
    description="读取文件",
    parameters=ReadParams,
    execute=read_execute,
)


def tool_msg(name: str, args: dict, call_id: str = "call-1") -> AssistantMessage:
    return AssistantMessage(
        content=[ToolCall(id=call_id, name=name, arguments=args)],
        stopReason="toolUse",
        timestamp=0,
    )


def text_msg(text: str) -> AssistantMessage:
    return AssistantMessage(content=[TextContent(text=text)], stopReason="stop", timestamp=0)


def make_scripted_stream(script: list[AssistantMessage]):
    """按调用次序返回预设消息的确定性 stream_fn（评估用，不烧 token）。"""
    calls = 0

    async def stream(context):
        nonlocal calls
        msg = script[min(calls, len(script) - 1)]
        calls += 1
        return msg

    return stream


def run(coro):
    return asyncio.run(coro)


def test_pass_when_checks_met():
    task = EvalTask(
        id="read-then-answer",
        prompt="读 a.txt",
        tools=[read_tool],
        checks=[tool_was_called("read"), tool_was_called_with("read", "path", "a.txt"), final_answer_contains("已完成")],
    )
    runner = EvalRunner(make_scripted_stream([tool_msg("read", {"path": "a.txt"}), text_msg("已完成读取")]))
    result = run(runner.run(task))

    assert result.passed is True
    assert result.failures == []
    assert result.trajectory.tool_calls[0].name == "read"
    assert result.trajectory.tool_calls[0].args == {"path": "a.txt"}
    assert result.score == 1.0


def test_fail_attribute_tool_error():
    # 模型调用了一个不存在的工具 -> 工具出错 -> 归因 tool_error
    task = EvalTask(id="bad-tool", prompt="调用不存在的工具", checks=[no_tool_errors()])
    runner = EvalRunner(make_scripted_stream([tool_msg("nonexistent", {}), text_msg("done")]))
    result = run(runner.run(task))

    assert result.passed is False
    assert result.failures[0].kind == "tool_error"


def test_fail_attribute_no_tool_called():
    # 模型直接回答、没调工具，但检查项期望调用 read
    task = EvalTask(id="no-tool", prompt="直接回答", checks=[tool_was_called("read")])
    runner = EvalRunner(make_scripted_stream([text_msg("直接回答")]), tools=[read_tool])
    result = run(runner.run(task))

    assert result.passed is False
    assert result.failures[0].kind == "no_tool_called"


def test_regression_case_from_failure():
    task = EvalTask(id="no-tool", prompt="直接回答", checks=[tool_was_called("read")])
    runner = EvalRunner(make_scripted_stream([text_msg("直接回答")]), tools=[read_tool])
    result = run(runner.run(task))

    case = to_regression_case(task, result)
    assert case.task_id == "no-tool"
    assert case.failed_checks == ["tool_was_called('read')"]
    assert case.failures[0].kind == "no_tool_called"
