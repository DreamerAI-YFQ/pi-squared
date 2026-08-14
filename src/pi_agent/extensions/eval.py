"""评估（对应 ETCLOVG 的 V 层，特色实现）。

完整闭环：任务定义 -> 运行 -> 结果 -> 失败归因 -> 回归用例。

核心思路：
- 用 `run_agent_loop` 的 emit 回调收集「轨迹」（调了哪些工具、参数、是否出错、跑了几回合）。
- 用「检查器 Check」对轨迹做断言（最后回复是否包含某段话、是否调用了某工具等）。
- 全过即 pass；否则把失败的检查项映射到「失败归因 Failure」（工具出错 / 步数超预算 / 没调工具 / 答案不符）。
- 失败轨迹可转成「回归用例 RegressionCase」存档，便于之后重跑。

这样就把 pi 里基本空白的 V 层补成一条可运行的验证流水线。
"""
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from pi_agent.agent_loop import AgentLoopConfig, run_agent_loop
from pi_agent.events import ToolExecutionEnd, ToolExecutionStart, TurnStart
from pi_agent.stream_fn import StreamFn
from pi_agent.types import AgentContext, AgentTool, Message, UserMessage


# ============ 轨迹 ============

@dataclass
class ToolCallRecord:
    """一次工具调用的证据快照。"""
    name: str
    args: dict
    is_error: bool
    result_text: str = ""


@dataclass
class Trajectory:
    """一次运行留下的轨迹：消息 + 工具调用 + 回合数。"""
    messages: list[Message] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    turns: int = 0

    def final_assistant_text(self) -> str:
        """最后一个助手消息的文本（检查器常用）。"""
        for m in reversed(self.messages):
            if m.role == "assistant":
                texts = [c.text for c in m.content if c.type == "text"]
                return "\n".join(texts)
        return ""

    def called_tool_names(self) -> list[str]:
        return [c.name for c in self.tool_calls]


# ============ 检查器 ============

@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


Check = Callable[[Trajectory], CheckResult]


def final_answer_contains(substring: str, name: str | None = None) -> Check:
    """检查最后回复是否包含指定子串。"""

    def check(t: Trajectory) -> CheckResult:
        text = t.final_assistant_text()
        passed = substring in text
        return CheckResult(
            name=name or f"final_answer_contains({substring!r})",
            passed=passed,
            detail=f"最后回复为: {text!r}",
        )

    return check


def tool_was_called(tool_name: str, name: str | None = None) -> Check:
    """检查是否调用过某工具。"""

    def check(t: Trajectory) -> CheckResult:
        called = t.called_tool_names()
        passed = tool_name in called
        return CheckResult(
            name=name or f"tool_was_called({tool_name!r})",
            passed=passed,
            detail=f"实际调用: {called}",
        )

    return check


def tool_was_called_with(tool_name: str, arg_key: str, arg_value, name: str | None = None) -> Check:
    """检查是否以指定参数调用过某工具。"""

    def check(t: Trajectory) -> CheckResult:
        for c in t.tool_calls:
            if c.name == tool_name and c.args.get(arg_key) == arg_value:
                return CheckResult(
                    name=name or f"tool_was_called_with({tool_name!r}, {arg_key}={arg_value!r})",
                    passed=True,
                    detail="命中",
                )
        return CheckResult(
            name=name or f"tool_was_called_with({tool_name!r}, {arg_key}={arg_value!r})",
            passed=False,
            detail=f"未找到该参数组合，实际工具调用: {[(c.name, c.args) for c in t.tool_calls]}",
        )

    return check


def no_tool_errors(name: str | None = None) -> Check:
    """检查轨迹里没有任何工具出错。"""

    def check(t: Trajectory) -> CheckResult:
        errs = [c.name for c in t.tool_calls if c.is_error]
        passed = not errs
        return CheckResult(
            name=name or "no_tool_errors",
            passed=passed,
            detail=f"出错工具: {errs}",
        )

    return check


# ============ 任务 / 结果 / 归因 ============

@dataclass
class EvalTask:
    """一次评估任务：给 agent 什么输入，期望什么结果。"""
    id: str
    prompt: str
    checks: list[Check]
    description: str = ""
    system_prompt: str = ""
    tools: list[AgentTool] = field(default_factory=list)
    max_turns: int = 8


@dataclass
class Failure:
    """一条失败归因：失败原因类别 + 证据。"""
    kind: str
    detail: str


@dataclass
class EvalResult:
    task_id: str
    passed: bool
    checks: list[CheckResult]
    failures: list[Failure]
    trajectory: Trajectory
    score: float = 0.0


def attribute_failures(task: EvalTask, trajectory: Trajectory, check_results: list[CheckResult]) -> list[Failure]:
    """把失败的检查项映射到根因类别。

    优先级（从具体到笼统）：
    1. 工具出错（tool_error）
    2. 步数超预算（step_budget_exceeded）
    3. 完全没调工具（no_tool_called）
    4. 兜底：答案不符（wrong_answer）
    """
    failures: list[Failure] = []
    for cr in check_results:
        if cr.passed:
            continue

        tool_errors = [c for c in trajectory.tool_calls if c.is_error]
        if tool_errors:
            names = ", ".join(c.name for c in tool_errors)
            failures.append(Failure("tool_error", f"工具出错（{names}）导致检查项「{cr.name}」未通过"))
            continue

        if trajectory.turns >= task.max_turns:
            failures.append(Failure(
                "step_budget_exceeded",
                f"跑了 {trajectory.turns} 回合，达到预算 {task.max_turns}，检查项「{cr.name}」未通过",
            ))
            continue

        if not trajectory.tool_calls:
            failures.append(Failure("no_tool_called", "轨迹中没有任何工具调用"))
            continue

        failures.append(Failure("wrong_answer", f"检查项「{cr.name}」未通过：{cr.detail}"))

    return failures


# ============ 运行器 ============

class EvalRunner:
    """评估运行器：注入一个确定性的 stream_fn 来跑 agent_loop。

    用 stream_fn 而非真实模型，保证评估可重复、可离线、不烧 token。
    """

    def __init__(self, stream_fn: StreamFn, tools: list[AgentTool] | None = None):
        self._stream_fn = stream_fn
        self._tools = tools or []

    async def run(self, task: EvalTask) -> EvalResult:
        trajectory = Trajectory()
        tools = task.tools or self._tools
        context = AgentContext(systemPrompt=task.system_prompt, messages=[], tools=tools)

        pending_args: dict[str, dict] = {}

        async def emit(event) -> None:
            if isinstance(event, TurnStart):
                trajectory.turns += 1
            elif isinstance(event, ToolExecutionStart):
                pending_args[event.toolCallId] = event.args
            elif isinstance(event, ToolExecutionEnd):
                result_text = "".join(c.text for c in event.result.content if c.type == "text")
                trajectory.tool_calls.append(ToolCallRecord(
                    name=event.toolName,
                    args=pending_args.pop(event.toolCallId, {}),
                    is_error=event.isError,
                    result_text=result_text,
                ))

        prompt = UserMessage(content=task.prompt, timestamp=int(time.time() * 1000))
        config = AgentLoopConfig(stream_fn=self._stream_fn)
        messages = await run_agent_loop([prompt], context, config, emit)
        trajectory.messages = messages

        check_results = [check(trajectory) for check in task.checks]
        passed = all(c.passed for c in check_results)
        score = (sum(1 for c in check_results if c.passed) / len(check_results)) if check_results else 1.0
        failures = attribute_failures(task, trajectory, check_results) if not passed else []

        return EvalResult(
            task_id=task.id,
            passed=passed,
            checks=check_results,
            failures=failures,
            trajectory=trajectory,
            score=score,
        )


# ============ 回归用例 ============

@dataclass
class RegressionCase:
    """失败轨迹转成的回归用例：记录复现失败所需的最小信息。"""
    task_id: str
    prompt: str
    system_prompt: str
    failed_checks: list[str]
    failures: list[Failure]


def to_regression_case(task: EvalTask, result: EvalResult) -> RegressionCase:
    """把一次失败的评估结果转成回归用例。"""
    failed_checks = [c.name for c in result.checks if not c.passed]
    return RegressionCase(
        task_id=task.id,
        prompt=task.prompt,
        system_prompt=task.system_prompt,
        failed_checks=failed_checks,
        failures=result.failures,
    )
