"""AgentEvent → JSON 可序列化字典。

事件是 dataclass（控制流通知），内部字段可能是 pydantic 模型（消息）、
列表、字典的任意嵌套，这里统一递归转换。
"""
import dataclasses
from typing import Any

from pydantic import BaseModel


def to_jsonable(value: Any) -> Any:
    """递归把 pydantic / dataclass / 容器转成纯 JSON 结构。"""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    return value


def serialize_event(event: Any) -> dict:
    """把一个 AgentEvent 序列化为 dict（含 type 字段）。"""
    return to_jsonable(event)
