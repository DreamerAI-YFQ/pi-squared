from typing import Awaitable, Callable # 异步可调对象类型，用于定义异步函数

from pi_agent.types import AgentContext, AssistantMessage
# 导入代理上下文和助手消息类型

# P0 简化版 StreamFn：接收上下文，返回完整助手消息。
# pi 里 StreamFn 返回的是流式事件流（start/text_delta/.../done），
# 流式能力放到 P1「自写流式层」再实现；P0 先聚焦 ReAct 循环逻辑。
StreamFn = Callable[[AgentContext], Awaitable[AssistantMessage]] 
# 定义异步函数类型，接收上下文，返回助手消息


# 这个文件定义了一个函数类型的规范，用人话解释就是：

# 它定义了"问一次模型"的标准接口
# StreamFn = Callable[[AgentContext], Awaitable[AssistantMessage]]
# 人话解释
# 就像规定了一个"打电话"的标准动作：

# 输入：给你一个"记忆包"（AgentContext，包含对话历史、系统提示词、可用工具）
# 输出：打完电话后，对方给你一个完整的回复（AssistantMessage）
# 特点：这是异步的（Awaitable），因为打电话需要时间，不能马上拿到结果
# 为什么需要这个？
# 因为：

# 系统里可能换不同的大模型（OpenAI、DeepSeek、Claude 等）
# 每个模型的调用方式不一样
# 但都需要"输入上下文，输出回复"这个基本动作
# 所以定义一个统一的标准，让系统不管用哪个模型都能正常工作
# 注释说明的
# P0 简化版：现在是最简单版本，返回完整的消息
# 原版是流式的：真正的版本应该像打字机一样逐字返回（StreamStart、TextDelta...、StreamDone）
# 流式放 P1：复杂的东西后面再做，现在先把基本对话逻辑搞定
# 总结：这就是"问模型一次"的标准动作定义，规定"给你什么，你要返回什么"。