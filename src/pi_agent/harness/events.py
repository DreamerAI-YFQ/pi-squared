from dataclasses import dataclass
from typing import Callable


@dataclass
class WatchHandle:
    """watch 返回的句柄：历史快照 + 继续订阅后续事件。"""
    snapshot: list
    start: Callable[[Callable], Callable[[], None]]


class EventBus:
    """按事件类型订阅/广播的事件总线，附带 watch（历史快照）。

    对应 pi 的 harness/events.ts 的 HarnessEventBus。
    """

    def __init__(self):
        self._listeners: dict[str, list[Callable]] = {}
        self._watch_listeners: list[Callable] = []
        self._history: list = []

    def on(self, event_type: str, listener: Callable) -> Callable[[], None]:
        """订阅某类型事件，返回取消订阅函数。"""
        self._listeners.setdefault(event_type, []).append(listener)

        def unsubscribe() -> None:
            self._listeners[event_type].remove(listener)

        return unsubscribe

    def emit(self, event) -> None:
        """广播事件：记录历史，并通知注册了该类型的 listener 和 watch listener。"""
        self._history.append(event)
        for listener in list(self._listeners.get(event.type, [])):
            listener(event)
        for listener in list(self._watch_listeners):
            listener(event)

    def watch(self) -> WatchHandle:
        """返回历史快照，并可继续订阅后续所有事件。"""
        snapshot = list(self._history)

        def start(listener: Callable) -> Callable[[], None]:
            self._watch_listeners.append(listener)

            def unsubscribe() -> None:
                self._watch_listeners.remove(listener)

            return unsubscribe

        return WatchHandle(snapshot=snapshot, start=start)
