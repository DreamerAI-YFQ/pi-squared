import asyncio # 异步编程库
import time # 时间库，用于获取当前时间戳
from typing import Awaitable, Callable # 异步函数类型，用于定义事件触发函数

from pi_agent.agent_loop import AgentLoopConfig, run_agent_loop # 导入智能循环配置类和核心 ReAct 循环
from pi_agent.events import AgentEvent  #导入智能循环事件类
from pi_agent.stream_fn import StreamFn  # 导入流函数，用于处理模型输出
from pi_agent.types import AgentContext, AgentTool, AgentToolResult, Message, ToolCall, UserMessage  # 导入智能体上下文、工具、消息、用户消息类型


Listener = Callable[[AgentEvent], Awaitable[None] | None]
# 定义异步函数类型，接收事件，返回无，用于触发事件

class Agent:
    """有状态智能体：持有对话历史，封装无状态循环，支持事件订阅。

    对应 pi 的 agent.ts。核心设计：
    - state 通过 message_end 事件累积（对应 pi 的 processEvents），
      而非使用 run_agent_loop 的返回值，二者数据流解耦。
    - steer/followUp 队列：运行中/停止后插入消息（P4 补全）。
    """

    def __init__(
        self, # 初始化智能体
        stream_fn: StreamFn, # 流函数，用于处理模型输出
        system_prompt: str = "", # 系统提示，用于引导智能体行为
        tools: list[AgentTool] | None = None, # 可用工具列表
        initial_messages: list[Message] | None = None, # 初始历史消息（从 session 恢复）
        before_tool_call: Callable[[ToolCall, dict], Awaitable[dict | None]] | None = None, # 工具执行前钩子（治理）
        after_tool_call: Callable[[ToolCall, AgentToolResult, bool], Awaitable[dict | None]] | None = None, # 工具执行后钩子（审计）
    ):
        self._stream_fn = stream_fn # 流函数，用于处理模型输出
        self._system_prompt = system_prompt # 系统提示，用于引导智能体行为
        self._messages: list[Message] = list(initial_messages) if initial_messages else [] # 历史消息列表
        self._tools: list[AgentTool] = tools or [] # 可用工具列表
        self._before_tool_call = before_tool_call # 工具执行前钩子
        self._after_tool_call = after_tool_call # 工具执行后钩子
        self._listeners: set[Listener] = set() # 事件监听者集合
        self._steering_queue: list[Message] = [] # steering 消息队列（运行中插入）
        self._follow_up_queue: list[Message] = [] # followUp 消息队列（停止后继续）
        self._running = False # 是否正在运行智能循环
        self._task: asyncio.Task[None] | None = None # 当前运行任务，用于取消或等待

    @property # 获取历史消息列表
    def messages(self) -> list[Message]:
        return self._messages

    @property # 获取是否正在运行智能循环
    def is_running(self) -> bool:
        return self._running

    def subscribe(self, listener: Listener) -> Callable[[], None]: # 订阅事件
        """订阅事件，返回取消订阅函数。"""
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def abort(self) -> None: # 取消当前运行
        """取消当前运行。"""
        if self._task and not self._task.done():
            self._task.cancel()

    async def wait_for_idle(self) -> None: # 等待当前运行结束
        """等待当前运行结束。"""
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def steer(self, message: Message) -> None: # 运行中插入 steering 消息
        """运行中插入 steering 消息（当前回合结束后注入）。"""
        self._steering_queue.append(message)

    def follow_up(self, message: Message) -> None: # agent 停止后插入 followUp 消息
        """agent 本应停止后插入 followUp 消息。"""
        self._follow_up_queue.append(message)

    async def prompt(self, text: str) -> None: # 发起一次用户提问
        """发起一次用户提问。"""
        if self._running:
            raise RuntimeError("Agent 正在运行，请先等待完成")
        message = UserMessage(content=text, timestamp=int(time.time() * 1000))
        await self._run([message])

    async def _run(self, prompts: list[Message]) -> None: # 运行智能循环
        """运行智能循环，处理用户提问。"""
        self._running = True
        self._task = asyncio.current_task()
        context = AgentContext( # 初始化当前上下文
            systemPrompt=self._system_prompt,
            messages=self._messages,
            tools=self._tools,
        )
        config = AgentLoopConfig(
            stream_fn=self._stream_fn,
            get_steering_messages=self._drain_steering,
            get_follow_up_messages=self._drain_follow_up,
            before_tool_call=self._before_tool_call,
            after_tool_call=self._after_tool_call,
        )
        try:
            await run_agent_loop(prompts, context, config, self._dispatch) # 运行智能循环
            # 这里不返回任何消息，因为智能循环通过 message_end 事件累积状态
        finally:
            self._running = False
            self._task = None

    async def _drain_steering(self) -> list[Message]: # 取出并清空 steering 队列
        messages = self._steering_queue
        self._steering_queue = []
        return messages

    async def _drain_follow_up(self) -> list[Message]: # 取出并清空 followUp 队列
        messages = self._follow_up_queue
        self._follow_up_queue = []
        return messages

    async def _dispatch(self, event: AgentEvent) -> None: # 分发事件 
        """更新内部状态并分发事件给监听者（对应 pi 的 processEvents）。"""
        if event.type == "message_end":
            self._messages.append(event.message)
        for listener in list(self._listeners):
            result = listener(event)
            if asyncio.iscoroutine(result):
                await result
