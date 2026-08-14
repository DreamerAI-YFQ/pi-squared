from dataclasses import dataclass

from pi_agent.harness.events import EventBus


@dataclass
class FooEvent:
    type: str = "foo"


@dataclass
class BarEvent:
    type: str = "bar"


def test_on_and_emit_routes_by_type():
    bus = EventBus()
    received = []
    bus.on("foo", lambda e: received.append(e))

    bus.emit(FooEvent())
    bus.emit(BarEvent())

    assert len(received) == 1
    assert received[0].type == "foo"


def test_watch_snapshot():
    bus = EventBus()
    bus.emit(FooEvent())
    bus.emit(BarEvent())

    handle = bus.watch()
    assert len(handle.snapshot) == 2


def test_watch_start_receives_future():
    bus = EventBus()
    received = []
    handle = bus.watch()
    handle.start(lambda e: received.append(e))

    bus.emit(FooEvent())
    bus.emit(BarEvent())

    assert len(received) == 2


def test_unsubscribe():
    bus = EventBus()
    received = []
    unsubscribe = bus.on("foo", lambda e: received.append(e))

    bus.emit(FooEvent())
    unsubscribe()
    bus.emit(FooEvent())

    assert len(received) == 1
