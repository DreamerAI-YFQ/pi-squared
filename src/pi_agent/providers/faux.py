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
