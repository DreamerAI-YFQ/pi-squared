import json
import os
import time

import httpx

from pi_agent.streaming.retry import RetryConfig, with_retry
from pi_agent.streaming.sse import parse_sse
from pi_agent.streaming.tool_call import ToolCallAccumulator
from pi_agent.types import (
    AgentContext,
    AssistantMessage,
    TextContent,
    ToolCall,
    ToolResultMessage,
    Usage,
    UserMessage,
)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


def _load_dotenv(path: str = ".env") -> None:
    """从 .env 文件加载 KEY=VALUE 到环境变量（不覆盖已存在的）。"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if not sep:
                continue
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                value = value[1:-1]
            os.environ.setdefault(key, value)


def _content_to_text(content) -> str:
    """从消息 content（字符串或内容块列表）提取纯文本。"""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, TextContent):
            parts.append(block.text)
    return "".join(parts)


def _to_openai_messages(messages):
    """把我们的 Message 列表转换成 OpenAI Chat Completions 的 messages 格式。"""
    result = []
    for msg in messages:
        if isinstance(msg, UserMessage):
            result.append({"role": "user", "content": _content_to_text(msg.content)})
        elif isinstance(msg, AssistantMessage):
            text = _content_to_text(msg.content)
            entry = {"role": "assistant", "content": text or None}
            tool_calls = [c for c in msg.content if isinstance(c, ToolCall)]
            if tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in tool_calls
                ]
            result.append(entry)
        elif isinstance(msg, ToolResultMessage):
            result.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.toolCallId,
                    "content": _content_to_text(msg.content),
                }
            )
    return result


def _to_openai_tools(tools):
    """把我们的 AgentTool 列表转换成 OpenAI 的 tools 格式。"""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters.model_json_schema(),
            },
        }
        for tool in tools
    ]


def _error_message(text: str) -> AssistantMessage:
    return AssistantMessage(
        content=[TextContent(text=text)],
        stopReason="error",
        errorMessage=text,
        timestamp=int(time.time() * 1000),
    )


class HTTPError(Exception):
    """带状态码的 HTTP 错误（非 200 时抛出）。"""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}")


def _should_retry(exc: Exception) -> bool:
    """哪些错误值得重试：429/408/5xx、超时、网络错误。"""
    if isinstance(exc, HTTPError):
        return exc.status_code in (408, 429) or exc.status_code >= 500
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.TransportError):
        return True
    return False


async def _fetch_sse(api_key: str, payload: dict, headers: dict) -> str:
    """发送流式请求并读取完整 SSE 文本；非 200 抛 HTTPError。"""
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=None)) as client:
        async with client.stream(
            "POST",
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
        ) as response:
            if response.status_code != 200:
                body = (await response.aread()).decode("utf-8", errors="replace")
                raise HTTPError(response.status_code, body)
            sse_text = ""
            async for chunk in response.aiter_text():
                sse_text += chunk
            return sse_text


async def deepseek_stream(context: AgentContext) -> AssistantMessage:
    """DeepSeek 的 OpenAI 兼容流式 provider。

    内部：流式调用 → SSE 解析 → 累积文本 + tool-call 增量 → 返回完整 AssistantMessage。
    对外保持 P0 的 StreamFn 签名（返回完整消息），agent_loop 无需改动。
    """
    _load_dotenv()
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return _error_message("未设置 DEEPSEEK_API_KEY 环境变量")

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": _to_openai_messages(context.messages),
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if context.tools:
        payload["tools"] = _to_openai_tools(context.tools)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    text_parts: list[str] = []
    accumulators: dict[int, ToolCallAccumulator] = {}

    try:
        sse_text = await with_retry(
            lambda: _fetch_sse(api_key, payload, headers),
            config=RetryConfig(max_retries=3, base_delay=1.0, max_delay=30.0),
            should_retry=_should_retry,
        )
    except HTTPError as exc:
        return _error_message(f"HTTP {exc.status_code}: {exc.body}")
    except httpx.HTTPError as exc:
        return _error_message(f"请求失败: {exc}")

    # 解析 SSE 流，累积文本和 tool-call 参数
    usage = None
    for _, data in parse_sse(sse_text):
        if data.strip() == "[DONE]":
            break
        chunk = json.loads(data)
        if chunk.get("usage"):
            usage = Usage(**chunk["usage"])
        choices = chunk.get("choices", [])
        if not choices:
            continue
        delta = choices[0].get("delta") or {}

        if delta.get("content"):
            text_parts.append(delta["content"])

        for tc in delta.get("tool_calls", []):
            index = tc.get("index", 0)
            if index not in accumulators:
                function = tc.get("function", {})
                accumulators[index] = ToolCallAccumulator(
                    tool_call_id=tc.get("id", ""),
                    name=function.get("name", ""),
                )
            function = tc.get("function", {})
            if function.get("arguments"):
                accumulators[index].add_delta(function["arguments"])

    # 组装最终 AssistantMessage
    content = []
    if text_parts:
        content.append(TextContent(text="".join(text_parts)))
    tool_calls = [acc.finalize() for acc in accumulators.values()]
    content.extend(tool_calls)

    return AssistantMessage(
        content=content,
        stopReason="toolUse" if tool_calls else "stop",
        timestamp=int(time.time() * 1000),
        usage=usage,
    )
