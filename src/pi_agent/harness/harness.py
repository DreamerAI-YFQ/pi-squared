"""编排层门面（对应 pi 的 agent-harness.ts 的核心接口，按需实现）。

把 Agent（循环）+ 工具 + session + compaction 组装成一个 coding agent 后端。
"""
import time

from pi_agent.agent import Agent, Listener
from pi_agent.harness.session.context import build_session_context
from pi_agent.harness.session.session import Session
from pi_agent.harness.tools.types import HarnessTool, ToolContext, bind_tool
from pi_agent.stream_fn import StreamFn
from pi_agent.types import AgentTool, Message, UserMessage


def _now_ms() -> int:
    return int(time.time() * 1000)


class AgentHarness:
    """把 Agent + 工具 + session 组装成 coding agent 后端。

    prompt 时从 session 恢复历史对话，运行后把新消息持久化回 session。
    """

    def __init__(
        self,
        stream_fn: StreamFn,
        env,
        session: Session,
        harness_tools: list[HarnessTool] | None = None,
        system_prompt: str = "",
        before_tool_call=None,
        after_tool_call=None,
        event_listeners: list[Listener] | None = None,
    ):
        self._stream_fn = stream_fn
        self._env = env
        self._session = session
        self._harness_tools: list[HarnessTool] = harness_tools or []
        self._system_prompt = system_prompt
        self._before_tool_call = before_tool_call
        self._after_tool_call = after_tool_call
        self._event_listeners: list[Listener] = event_listeners or []
        self._agent: Agent | None = None

    async def prompt(self, text: str) -> list[Message]:
        """发起一次提问：恢复历史 → 跑循环 → 持久化新消息。"""
        # 1. 从 session 恢复历史
        entries = await self._session.find_entries()
        entries_sorted = sorted(entries, key=lambda e: e.seq)
        history = build_session_context(entries_sorted)
        history_len = len(history)

        # 2. 绑定工具 + 构造 Agent
        bound_tools: list[AgentTool] = [
            bind_tool(tool, ToolContext(env=self._env)) for tool in self._harness_tools
        ]
        agent = Agent(
            stream_fn=self._stream_fn,
            system_prompt=self._system_prompt,
            tools=bound_tools,
            initial_messages=history,
            before_tool_call=self._before_tool_call,
            after_tool_call=self._after_tool_call,
        )
        for listener in self._event_listeners:
            agent.subscribe(listener)
        self._agent = agent

        # 3. 跑循环
        await agent.prompt(text)

        # 4. 只把新产生的消息持久化到 session（history 已在 session 里）
        for msg in agent.messages[history_len:]:
            await self._session.append_message(msg)

        return agent.messages

    def steer(self, text: str) -> None:
        """运行中插入 steering 消息。"""
        if self._agent:
            self._agent.steer(UserMessage(content=text, timestamp=_now_ms()))

    def follow_up(self, text: str) -> None:
        """agent 停止后插入 followUp 消息。"""
        if self._agent:
            self._agent.follow_up(UserMessage(content=text, timestamp=_now_ms()))
