from pi_agent.types import AgentContext, AssistantMessage, TextContent, ToolCall, ToolResultMessage
# 导入智能体上下文、助手消息、文本内容、工具调用、工具结果消息类型

async def faux_stream(context: AgentContext) -> AssistantMessage: # 假模型流函数
    """假模型：根据对话最后一条消息，决定返回「工具调用」还是「最终回答」。

    这就是最小 ReAct 里的"模型"：
    - 第一次调用时，最后一条是用户消息 -> 返回一个 read 工具调用
    - 第二次调用时，最后一条是工具结果 -> 返回最终回答
    """
    last = context.messages[-1] if context.messages else None

    if isinstance(last, ToolResultMessage): # 如果最后一条是工具结果消息
        return AssistantMessage(            # 返回最终回答
            content=[TextContent(text="已完成读取")],
            stopReason="stop",
            timestamp=0,
        )

    return AssistantMessage(            # 否则返回工具调用，调用 read 工具读取 a.txt
        content=[ToolCall(id="call-1", name="read", arguments={"path": "a.txt"})],
        stopReason="toolUse",
        timestamp=0,
    )


# 我来用一个具体的对话流程来解释这个假模型的工作原理：

# 具体例子
# 第一次调用：用户刚发了消息
# # 假设 context.messages = [
# #     UserMessage(role="user", content="读取 a.txt", timestamp=100)
# # ]
# # 最后一条是用户消息（不是 ToolResultMessage）
# last = context.messages[-1]  # UserMessage
# # 判断：isinstance(last, ToolResultMessage) = False
# # 所以返回工具调用
# return AssistantMessage(
#     content=[ToolCall(id="call-1", name="read", arguments={"path": "a.txt"})],
#     stopReason="toolUse",  # 关键：告诉循环要继续
#     timestamp=0,
# )
# 人话解释：用户说"读取 a.txt"，假模型看了一下对话历史，发现用户刚发了消息，于是返回一个工具调用："我去读取 a.txt"。

# 第二次调用：工具执行完后
# # 假设 context.messages = [
# #     UserMessage(role="user", content="读取 a.txt", timestamp=100),
# #     AssistantMessage(role="assistant", content=[ToolCall(...)], stopReason="toolUse", timestamp=101),
# #     ToolResultMessage(role="toolResult", toolCallId="call-1", content=[...], timestamp=102)
# # ]
# # 最后一条是工具结果消息
# last = context.messages[-1]  # ToolResultMessage
# # 判断：isinstance(last, ToolResultMessage) = True
# # 所以返回最终回答
# return AssistantMessage(
#     content=[TextContent(text="已完成读取")],
#     stopReason="stop",  # 关键：告诉循环要结束
#     timestamp=0,
# )
# 人话解释：工具已经执行完了，假模型看了一下对话历史，发现最后一条是工具结果，于是返回最终回答："已完成读取"。

# 完整对话流程
# 用户说："读取 a.txt"
#     ↓
# 假模型调用一次 → 返回工具调用 (stopReason="toolUse")
#     ↓
# 系统执行 read 工具
#     ↓
# 假模型再调用一次 → 返回最终回答 (stopReason="stop")
#     ↓
# 循环结束，返回给用户
# 为什么叫"假模型"？
# 因为它不是真正的大模型，只是：

# 简单地看对话历史的最后一条消息
# 根据这条消息的类型决定返回什么
# 没有真正的 AI 思考过程
# 人话解释：就像一个只会按剧本演戏的演员，根据对话的最后一句来决定下一句说什么，用来测试系统的对话流程，不需要调用真实的 AI API。


#深度思考
# 关键点：工具不是"主动"返回，而是系统"被动"回填
# 完整流程
# 1. 大模型返回消息（包含工具调用）
#    AssistantMessage(content=[ToolCall(...)], stopReason="toolUse")
#         ↓
# 2. 系统提取工具调用
#    tool_calls = [c for c in assistant_msg.content if isinstance(c, ToolCall)]
#         ↓
# 3. 系统逐个执行工具
#    result = await execute_tool_call(current, tool_call, ...)
#         ↓
# 4. 系统把结果封装成消息
#    tool_result_msg = ToolResultMessage(
#        toolCallId=tool_call.id,
#        toolName=tool_call.name,
#        content=result.content,
#        isError=is_error,
#        timestamp=now_ms(),
#    )
#         ↓
# 5. 系统把结果加到对话历史
#    current.messages.append(tool_result_msg)
#    new_messages.append(tool_result_msg)
#         ↓
# 6. 循环继续，再次调用大模型
#    assistant_msg = await config.stream_fn(current)
#         ↓
# 7. 大模型看到对话历史里有工具结果
#    context.messages = [
#        ...,
#        AssistantMessage(content=[ToolCall(...)]),
#        ToolResultMessage(content=[...]),  ← 新增的工具结果
#    ]
#         ↓
# 8. 大模型根据工具结果继续思考
# 核心代码（来自 agent_loop.py）
# # 3. 逐个执行工具，把结果回填到上下文
# for tool_call in tool_calls:
#     # 执行工具
#     result, is_error = await execute_tool_call(current, tool_call, ...)
    
#     # 封装成消息
#     tool_result_msg = ToolResultMessage(
#         toolCallId=tool_call.id,
#         toolName=tool_call.name,
#         content=result.content,
#         isError=is_error,
#         timestamp=now_ms(),
#     )
    
#     # 关键：加到对话历史
#     current.messages.append(tool_result_msg)
#     new_messages.append(tool_result_msg)
# 人话解释
# 就像打电话：

# 你说"帮我查下天气"（用户消息）
# 朋友说"我去查"（模型返回工具调用）
# 朋友挂了电话去查天气（系统执行工具）
# 朋友查完又打回来告诉你"今天25度"（系统把结果加到对话历史）
# 朋友根据天气结果继续和你聊天（模型看到结果继续思考）
# 工具本身不会主动"打电话"给模型，而是系统执行完工具后，把结果"记"在对话历史里，下次调用模型时，模型就能看到这个结果。

# 为什么这样设计？
# 解耦：工具只负责执行，不负责和模型通信
# 统一：所有结果都通过消息系统传递
# 灵活：可以支持批量工具调用、并行执行等复杂场景



# 你观察得很准确！让我澄清一下：

# ## 实际实现确实主要是 append

# 从刚才读取的 `agent_loop.py` 代码可以看到：

# ```python
# # 关键：加到对话历史
# current.messages.append(tool_result_msg)
# new_messages.append(tool_result_msg)
# ```

# **人话解释**：工具执行完后，系统就是把结果消息直接 `append` 到对话历史列表的末尾，很简单粗暴。

# ## 但也有 hook 机制

# 在 `AgentLoopConfig` 中确实定义了 hook：

# ```python
# before_tool_call: Callable[[ToolCall, dict], Awaitable[dict | None]] | None = None  # 工具执行前钩子（可 block）
# after_tool_call: Callable[[ToolCall, AgentToolResult, bool], Awaitable[dict | None]] | None = None  # 工具执行后钩子（可覆写）
# ```

# ## 两者的区别

# | 机制 | 作用 | 用途 |
# |------|------|------|
# | **append** | 把结果加到对话历史 | **数据传递**：让模型下次调用时能看到结果 |
# | **hook** | 在工具执行前后插入自定义逻辑 | **横切关注**：日志、监控、权限检查、参数修改等 |

# ## 形象比喻

# - **append**：就像快递员把包裹放到你家门口（数据传递）
# - **hook**：就像你在门口装了摄像头，看到快递员来了可以拍照、记录、甚至拦截（横切逻辑）

# ## 总结

# - **核心数据流**：确实就是简单的 `append`，把工具结果加到对话历史
# - **扩展能力**：通过 hook 机制可以在工具执行前后插入自定义逻辑
# - **为什么这么设计**：append 处理核心数据流，hook 处理横切关注点，职责分离

