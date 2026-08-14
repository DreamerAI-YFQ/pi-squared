from dataclasses import dataclass
from typing import Generic, Literal, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")


@dataclass
class Ok(Generic[T]):
    value: T
    ok: Literal[True] = True


@dataclass
class Err(Generic[E]):
    error: E
    ok: Literal[False] = False


Result = Union[Ok[T], Err[E]]


def ok(value: T) -> Ok[T]:
    """构造成功结果。"""
    return Ok(value)


def err(error: E) -> Err[E]:
    """构造失败结果。"""
    return Err(error)


def is_ok(result) -> bool:
    return result.ok


def is_err(result) -> bool:
    return not result.ok


def get_or_throw(result: Ok[T]) -> T:
    """成功取值；失败则抛异常（error 是异常则原样抛，否则包成 RuntimeError）。"""
    if is_ok(result):
        return result.value
    error = result.error
    if isinstance(error, BaseException):
        raise error
    raise RuntimeError(str(error))


def get_or_undefined(result):
    """成功取值；失败返回 None。"""
    if is_ok(result):
        return result.value
    return None
