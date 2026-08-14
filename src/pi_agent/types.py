from dataclasses import dataclass, field # 数据类
from typing import Annotated, Any, Awaitable, Callable, Literal, Union

from pydantic import BaseModel, Field


# 停止原因：模型这一轮为什么结束（决定循环是否继续）
StopReason = Literal["pending", "stop", "length", "toolUse", "error", "aborted", "deferred"]


# ============ 第一层：内容块（最底层，不依赖别的） ============

class TextContent(BaseModel):
    type: Literal["text"] = "text" # 文本内容
    text: str # 文本内容文本


class ImageContent(BaseModel): # 图片内容
    type: Literal["image"] = "image" # 图片内容
    data: str          # base64 编码的图片数据
    mimeType: str      # 例如 "image/png"


class ToolCall(BaseModel): # 工具调用内容
    type: Literal["toolCall"] = "toolCall" # 工具调用内容
    id: str # 工具调用 ID
    name: str # 工具名称
    arguments: dict[str, Any] # 工具调用参数，键值对格式


# ============ 第二层：消息（引用第一层的内容块） ============

class UserMessage(BaseModel):
    role: Literal["user"] = "user" # 用户消息
    content: str | list[TextContent | ImageContent] # 用户消息内容
    timestamp: int # 用户消息时间戳


class Usage(BaseModel):
    """一次 LLM 调用的 token 用量（对应 OpenAI/DeepSeek 的 usage）。"""
    prompt_tokens: int = 0 # 输入 token 数
    completion_tokens: int = 0 # 输出 token 数
    total_tokens: int = 0 # 总 token 数


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant" # 助手消息
    content: list[TextContent | ImageContent | ToolCall] # 助手消息内容
    stopReason: StopReason # 助手消息停止原因
    timestamp: int # 助手消息时间戳
    errorMessage: str | None = None # 助手消息错误信息
    usage: Usage | None = None # token 用量（provider 回传，用于成本追踪）


class ToolResultMessage(BaseModel):
    role: Literal["toolResult"] = "toolResult" # 工具调用结果消息
    toolCallId: str # 工具调用 ID
    toolName: str # 工具名称
    content: list[TextContent | ImageContent] # 工具调用结果消息内容
    isError: bool = False # 是否错误
    timestamp: int # 工具调用结果消息时间戳


# ============ 第三层：消息联合（靠 role 字段自动判别三种消息） ============

Message = Annotated[
    Union[UserMessage, AssistantMessage, ToolResultMessage], # 消息联合
    Field(discriminator="role"), # 消息联合的 discriminator 字段
]


# ============ 第四层：工具 + 上下文 ============

class AgentToolResult(BaseModel):
    content: list[TextContent | ImageContent]  # 返回给模型的内容
    details: dict[str, Any] = {}               # 结构化细节，给 UI/日志用
    terminate: bool = False                    # 是否要提前结束这一批工具


@dataclass                                          #定义一个数据类专用，用@dataclass装饰器
class AgentTool:
    name: str                                       # 工具名，模型靠它调用
    description: str                                # 给模型看的"何时用"说明
    parameters: type[BaseModel]                     # 参数 schema：一个 pydantic 模型类
    execute: Callable[[str, dict], Awaitable[AgentToolResult]]  
    # 执行函数，接收 tool_call_id 和 params，返回 AgentToolResult
    label: str = ""                                 # UI 显示名（P0 可留空）
    executionMode: Literal["sequential", "parallel"] = "parallel"  # 执行模式，顺序或并行


@dataclass
class AgentContext:
    systemPrompt: str                               # 系统提示词
    messages: list[Message]                         # 对话历史，代表模型和用户之间所有的交互记录
    tools: list[AgentTool] = field(default_factory=list)  # 可用工具


# literal 翻译：限制变量的取值范围，只能是指定的值


# ============ 第五层：流式事件（模型流式输出的统一协议） ============
# 模型边吐 token 边发这些事件；provider 适配器负责把各家原始格式翻译成这套统一语言。

@dataclass
class StreamStart:
    partial: AssistantMessage                       # 初始的助手消息"壳"
    type: Literal["start"] = "start"


@dataclass
class TextDelta:
    delta: str                                      # 这次吐出的文本片段
    type: Literal["text_delta"] = "text_delta"


@dataclass
class ToolCallStart:
    toolCallId: str                                 # 工具调用 ID
    name: str                                       # 工具名
    type: Literal["toolcall_start"] = "toolcall_start"


@dataclass
class ToolCallDelta:
    toolCallId: str                                 # 工具调用 ID
    delta: str                                      # 参数增量（可能是残缺 JSON 片段）
    type: Literal["toolcall_delta"] = "toolcall_delta"


@dataclass
class StreamDone:
    message: AssistantMessage                       # 最终完整消息
    type: Literal["done"] = "done"


@dataclass
class StreamError:
    message: AssistantMessage                       # 出错时的消息（stopReason 为 error）
    type: Literal["error"] = "error"


AssistantMessageEvent = Union[ # 流式事件联合
    StreamStart,
    TextDelta,
    ToolCallStart,
    ToolCallDelta,
    StreamDone,
    StreamError,
]
