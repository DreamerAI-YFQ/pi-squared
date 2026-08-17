"""编排层门面（对应 pi 的 agent-harness.ts 的核心接口，按需实现）。

把 Agent（循环）+ 工具 + session + compaction 组装成一个 coding agent 后端。
"""
import time

from pi_agent.agent import Agent, Listener # Agent 是循环，Listener 是事件监听器
from pi_agent.harness.compaction import (
    CompactionSettings,
    DEFAULT_COMPACTION_SETTINGS,
    estimate_context_tokens,
    generate_summary,
    prepare_compaction,
    should_compact,
)
from pi_agent.harness.session.context import build_session_context # 构建会话上下文
from pi_agent.harness.session.session import Session # 会话
from pi_agent.harness.session.types import CompactionEntry
from pi_agent.harness.tools.types import HarnessTool, ToolContext, bind_tool # 工具类型
from pi_agent.stream_fn import StreamFn # 流函数
from pi_agent.types import AgentTool, Message, UserMessage # 消息类型


def _now_ms() -> int: # 获取当前时间戳，单位为毫秒
    return int(time.time() * 1000)


class AgentHarness:
    """把 Agent + 工具 + session 组装成 coding agent 后端。

    prompt 时从 session 恢复历史对话，运行后把新消息持久化回 session。
    """

    def __init__( # 初始化 AgentHarness
        self, # 实例化 AgentHarness
        stream_fn: StreamFn, # 流函数
        env, # 环境
        session: Session, # 会话
        harness_tools: list[HarnessTool] | None = None, # 工具
        system_prompt: str = "", # 系统提示
        before_tool_call=None, # 工具调用前回调
        after_tool_call=None, # 工具调用后回调
        event_listeners: list[Listener] | None = None, # 事件监听器
        compaction_settings: CompactionSettings = DEFAULT_COMPACTION_SETTINGS, # 压缩设置
    ):
        self._stream_fn = stream_fn # 流函数
        self._env = env
        self._session = session # 会话
        self._harness_tools: list[HarnessTool] = harness_tools or [] # 工具
        self._system_prompt = system_prompt # 系统提示
        self._before_tool_call = before_tool_call # 工具调用前回调
        self._after_tool_call = after_tool_call # 工具调用后回调
        self._event_listeners: list[Listener] = event_listeners or [] # 事件监听器
        self._compaction_settings = compaction_settings # 压缩设置
        self._agent: Agent | None = None # 代理

    async def prompt(self, text: str) -> list[Message]:
        """发起一次提问：恢复历史 → 压缩检查 → 跑循环 → 持久化新消息。"""
        # 1. 从 session 恢复历史
        entries = await self._session.find_entries()
        entries_sorted = sorted(entries, key=lambda e: e.seq)
        history = build_session_context(entries_sorted)
        history_len = len(history)

        # 2. 检查是否需要压缩上下文
        context_window = 128000  # 假设默认上下文窗口，实际应从模型配置获取
        history_tokens = estimate_context_tokens(history)
        if should_compact(history_tokens, context_window, self._compaction_settings):
            to_summarize, retained = prepare_compaction(history, self._compaction_settings)
            summary = await generate_summary(to_summarize, self._stream_fn)
            # 创建 CompactionEntry 并存入 session
            compaction_entry = CompactionEntry(
                summary=summary,
                retained_tail=retained,
                tokens_before=history_tokens,
            )
            await self._session.append_entry(compaction_entry)
            # 用保留的尾部作为新的历史
            history = retained
            history_len = len(history)

        # 3. 绑定工具 + 构造 Agent
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
