import asyncio #异步事件流
from typing import AsyncIterator, Callable, Generic, TypeVar #类型提示

from pi_agent.types import AssistantMessage, AssistantMessageEvent, StreamDone, StreamError #类型提示

#类型提示
T = TypeVar("T") #事件类型
R = TypeVar("R") #最终结果类型

# 哨兵：标记流结束。用 object() 而非 None，避免和真实事件混淆。
_SENTINEL = object()


class EventStream(Generic[T, R]):
    """异步事件流：生产者 push，消费者 async for 拉取。

    对应 pi 的 event-stream.ts。is_complete 判断终结事件，
    extract_result 从终结事件提取最终结果。
    """

    def __init__(self, is_complete: Callable[[T], bool], extract_result: Callable[[T], R]):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._is_complete = is_complete
        self._extract_result = extract_result
        self._done = False
        self._final_result: R | None = None

    def push(self, event: T) -> None:
        """推入一个事件；若它是终结事件，流结束并记录最终结果。"""
        if self._done:
            return
        if self._is_complete(event):
            self._done = True
            self._final_result = self._extract_result(event)
            self._queue.put_nowait(event)
            self._queue.put_nowait(_SENTINEL)
        else:
            self._queue.put_nowait(event)

    def end(self, result: R | None = None) -> None:
        """手动结束流，可选地提供最终结果。"""
        if self._done:
            return
        self._done = True
        if result is not None:
            self._final_result = result
        self._queue.put_nowait(_SENTINEL)

    async def __aiter__(self) -> AsyncIterator[T]:
        while True:
            event = await self._queue.get()
            if event is _SENTINEL:
                return
            yield event

    @property
    def final_result(self) -> R | None:
        return self._final_result


def create_assistant_message_stream() -> EventStream[AssistantMessageEvent, AssistantMessage]:
    """创建一个以 done/error 为终结事件、提取最终 AssistantMessage 的事件流。"""

    def is_complete(event: AssistantMessageEvent) -> bool:
        return event.type in ("done", "error")

    def extract_result(event: AssistantMessageEvent) -> AssistantMessage:
        if isinstance(event, (StreamDone, StreamError)):
            return event.message
        raise ValueError(f"非终结事件: {event.type}")

    return EventStream(is_complete, extract_result)
