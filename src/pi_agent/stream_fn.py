from typing import Awaitable, Callable # 异步可调对象类型，用于定义异步函数

from pi_agent.types import AgentContext, AssistantMessage

# P0 简化版 StreamFn：接收上下文，返回完整助手消息。
# pi 里 StreamFn 返回的是流式事件流（start/text_delta/.../done），
# 流式能力放到 P1「自写流式层」再实现；P0 先聚焦 ReAct 循环逻辑。
StreamFn = Callable[[AgentContext], Awaitable[AssistantMessage]] 
# 定义异步函数类型，接收上下文，返回助手消息
