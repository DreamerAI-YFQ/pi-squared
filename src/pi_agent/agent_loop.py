import time # 时间库，用于获取当前时间戳
from dataclasses import dataclass # 定义数据类，用于定义智能循环配置
from typing import Awaitable, Callable # 异步函数类型，用于定义事件触发函数
 
from pi_agent.events import ( # 导入智能循环事件类
    AgentEnd,
    AgentEvent,
    AgentStart,
    MessageEnd,
    MessageStart,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
    TurnStart,
)
from pi_agent.stream_fn import StreamFn  # 导入流函数，用于处理模型输出
from pi_agent.types import ( # 导入智能体上下文、工具结果、消息、文本内容、工具调用、工具结果消息类型
    AgentContext,
    AgentToolResult,
    Message,
    TextContent,
    ToolCall,
    ToolResultMessage,
)


@dataclass # 定义智能循环配置类，包含流函数
class AgentLoopConfig:
    stream_fn: StreamFn # 流函数，用于处理模型输出
    get_steering_messages: Callable[[], Awaitable[list[Message]]] | None = None  
    # steering 消息队列回调（运行中插入），返回steering消息列表
    get_follow_up_messages: Callable[[], Awaitable[list[Message]]] | None = None  
    # followUp 消息队列回调（停止后继续），返回followUp消息列表
    before_tool_call: Callable[[ToolCall, dict], Awaitable[dict | None]] | None = None  
    # 工具执行前钩子（可 block），返回是否阻断执行
    after_tool_call: Callable[[ToolCall, AgentToolResult, bool], Awaitable[dict | None]] | None = None  
    # 工具执行后钩子（可覆写），返回是否覆写结果；StreamFn = Callable[[AgentContext], Awaitable[AssistantMessage]]


Emit = Callable[[AgentEvent], Awaitable[None]] # 定义异步函数类型，接收事件，返回无，用于触发事件



def now_ms() -> int: # 获取当前时间戳（毫秒级）
    return int(time.time() * 1000)


async def run_agent_loop( # 核心 ReAct 循环
    prompts: list[Message], # 用户消息列表
    context: AgentContext, # 历史上下文，包含系统提示、历史对话、可用工具
    config: AgentLoopConfig, # 智能循环配置，包含流函数
    emit: Emit, # 事件触发函数，用于触发智能循环事件
) -> list[Message]: # 返回本轮产生的所有消息（含 prompt、助手消息、工具结果）
    """核心 ReAct 循环。

    prompts 是本次新增的用户消息；context 含历史对话与可用工具。
    返回本轮产生的所有消息（含 prompt、助手消息、工具结果）。
    """
    new_messages: list[Message] = list(prompts) # 初始化新消息列表，包含用户消息
    current = AgentContext( # 初始化当前上下文
        systemPrompt=context.systemPrompt, # 保持系统提示
        messages=[*context.messages, *prompts], # 合并历史对话与新消息
        tools=context.tools, # 保持可用工具
    )

    await emit(AgentStart()) # 触发智能循环开始事件
    await emit(TurnStart()) # 触发回合开始事件
    for prompt in prompts: # 遍历用户消息，触发消息开始事件和结束事件
        await emit(MessageStart(message=prompt)) # 触发用户消息开始事件
        await emit(MessageEnd(message=prompt)) # 触发用户消息结束事件

    pending_messages: list[Message] = await config.get_steering_messages() if config.get_steering_messages else []
    # 获取 steering 消息队列，如果为空，则返回空列表，否则返回steering消息列表
    first_turn = True # 第一回合标志

    # 外层循环：处理 follow-up（agent 本应停止后又来新消息）
    while True:
        has_more_tool_calls = True # 有更多工具调用标志

        # 内层循环：处理工具调用 + steering（运行中插入消息）
        while has_more_tool_calls or pending_messages: # 如果还有工具调用或steering消息，则继续循环
            if not first_turn: # 如果第二回合，则触发回合开始事件
                await emit(TurnStart()) # 触发回合开始事件
            else: # 如果第一回合，则不触发回合开始事件
                first_turn = False # 第一回合标志

            # 注入 pending 消息（steering 或 follow-up），如果steering消息不为空，则注入steering消息
            if pending_messages: # 如果steering消息不为空，则注入steering消息
                for msg in pending_messages: # 遍历steering消息
                    await emit(MessageStart(message=msg)) # 触发消息开始事件
                    await emit(MessageEnd(message=msg)) # 触发消息结束事件
                    current.messages.append(msg) # 将消息添加到当前上下文消息列表
                    new_messages.append(msg) # 将消息添加到新消息列表
                pending_messages = [] # 清空steering消息列表，等待下一回合

            # 1. 调用模型（注入的 stream_fn）
            assistant_msg = await config.stream_fn(current) # 调用流函数，获取助手消息
            current.messages.append(assistant_msg) # 将助手消息添加到当前上下文
            new_messages.append(assistant_msg) # 将助手消息添加到新消息列表
            await emit(MessageStart(message=assistant_msg)) # 触发助手消息开始事件
            await emit(MessageEnd(message=assistant_msg)) # 触发助手消息结束事件

            # 2. 提取模型要调用的工具
            tool_calls = [c for c in assistant_msg.content if isinstance(c, ToolCall)] # 提取助手消息中的工具调用
            tool_results: list[ToolResultMessage] = [] # 初始化工具结果列表
            has_more_tool_calls = False # 没有更多工具调用标志

            if tool_calls: # 如果工具调用不为空，则逐个执行工具
                # 3. 逐个执行工具，把结果回填到上下文
                for tool_call in tool_calls:
                    await emit(
                        ToolExecutionStart(toolCallId=tool_call.id, toolName=tool_call.name, args=tool_call.arguments) # 触发工具执行开始事件
                    )
                    result, is_error = await execute_tool_call(current, tool_call, config.before_tool_call, config.after_tool_call) # 执行工具调用
                    await emit(
                        ToolExecutionEnd(toolCallId=tool_call.id, toolName=tool_call.name, result=result, isError=is_error) # 触发工具执行结束事件
                    )
                    tool_result_msg = ToolResultMessage( # 创建工具结果消息
                        toolCallId=tool_call.id,
                        toolName=tool_call.name,
                        content=result.content,
                        isError=is_error,
                        timestamp=now_ms(), # 获取当前时间戳
                    )
                    tool_results.append(tool_result_msg) # 将工具结果消息添加到工具结果列表
                    current.messages.append(tool_result_msg) # 将工具结果消息添加到当前上下文
                    new_messages.append(tool_result_msg) # 将工具结果消息添加到新消息列表
                    await emit(MessageStart(message=tool_result_msg)) # 触发工具结果消息开始事件
                    await emit(MessageEnd(message=tool_result_msg)) # 触发工具结果消息结束事件
                has_more_tool_calls = True # 有更多工具调用标志

            await emit(TurnEnd(message=assistant_msg, toolResults=tool_results)) # 触发回合结束事件

            # poll steering 消息
            pending_messages = await config.get_steering_messages() if config.get_steering_messages else [] # 获取steering消息列表

        # 外层：poll follow-up 消息
        follow_up = await config.get_follow_up_messages() if config.get_follow_up_messages else [] # 获取followUp消息列表
        if follow_up: # 如果followUp消息不为空，则继续循环
            pending_messages = follow_up # 更新steering消息列表
            continue # 继续循环
        break # 退出循环

    await emit(AgentEnd(messages=new_messages)) # 触发代理结束事件
    return new_messages # 返回新消息列表


async def execute_tool_call( # 执行单调用
    context: AgentContext, # 当前上下文
    tool_call: ToolCall, # 工具调用消息
    before_tool_call=None, # 工具执行前钩子（可 block）
    after_tool_call=None, # 工具执行后钩子（可覆写）
) -> tuple[AgentToolResult, bool]: # 返回工具结果和是否错误
    """执行单个工具调用：找工具 -> 校验参数 -> before 钩子 -> 执行 -> after 钩子。"""
    tool = next((t for t in context.tools if t.name == tool_call.name), None) # 查找工具
    if tool is None: # 如果工具不存在
        return AgentToolResult( # 返回工具不存在的结果
            content=[TextContent(text=f"工具 {tool_call.name} 不存在")],
            details={},
        ), True

    try: 
        # 参数校验：用工具的 pydantic 参数模型校验传入的字典
        tool.parameters.model_validate(tool_call.arguments) # 校验参数
    except Exception as exc: # 如果参数校验失败
        return AgentToolResult(content=[TextContent(text=str(exc))], details={}), True # 返回参数校验错误的结果

    # beforeToolCall 钩子：可阻断执行（返回 {"block": True, "reason": ...}）
    if before_tool_call:
        before_result = await before_tool_call(tool_call, tool_call.arguments)
        if before_result and before_result.get("block"):
            reason = before_result.get("reason") or "工具执行被阻断"
            return AgentToolResult(content=[TextContent(text=reason)], details={}), True

    try: # 执行工具调用
        result = await tool.execute(tool_call.id, tool_call.arguments) # 执行工具调用
        is_error = False
    except Exception as exc: # 如果工具执行失败
        result = AgentToolResult(content=[TextContent(text=str(exc))], details={})
        is_error = True

    # afterToolCall 钩子：可覆写结果（返回 {"content": ..., "isError": ...}）
    if after_tool_call:
        after_result = await after_tool_call(tool_call, result, is_error)
        if after_result:
            if "content" in after_result:
                result.content = after_result["content"]
            if "isError" in after_result:
                is_error = after_result["isError"]

    return result, is_error
