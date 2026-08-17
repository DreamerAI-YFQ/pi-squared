"""
Result 类型：Rust 风格的错误处理机制。

用于显式表达操作可能成功或失败，替代传统的异常抛出。
对应 pi 的 result.ts。

核心思想：
- Result[T, E] 要么是 Ok[T]（成功，包含值 T），要么是 Err[E]（失败，包含错误 E）
- 强制调用者显式处理错误，避免"可能抛异常"的隐式失败
- 类型安全：编译时就能检查错误处理逻辑

使用场景：
- 工具调用（read/write/bash）可能失败，需要统一错误表示
- Agent 循环中需要根据结果决定下一步（重试/放弃/降级）
- 函数式组合：多步操作中失败就短路
"""
from dataclasses import dataclass
from typing import Generic, Literal, TypeVar, Union

# 泛型类型参数：T 是成功值的类型，E 是错误的类型
T = TypeVar("T")
E = TypeVar("E")


@dataclass
class Ok(Generic[T]):
    """成功结果：包含操作成功后的值。"""
    value: T  # 成功返回的值
    ok: Literal[True] = True  # 类型标记，用于运行时判断是 Ok 还是 Err


@dataclass
class Err(Generic[E]):
    """失败结果：包含错误信息。"""
    error: E  # 错误信息（可以是字符串、异常对象、自定义错误类型等）
    ok: Literal[False] = False  # 类型标记，用于运行时判断是 Ok 还是 Err


# Result 类型别名：要么是 Ok[T]，要么是 Err[E]
Result = Union[Ok[T], Err[E]]


def ok(value: T) -> Ok[T]:
    """构造成功结果。

    Args:
        value: 成功时返回的值

    Returns:
        Ok[T] 包装的成功结果
    """
    return Ok(value)


def err(error: E) -> Err[E]:
    """构造失败结果。

    Args:
        error: 错误信息（可以是字符串、异常对象等）

    Returns:
        Err[E] 包装的失败结果
    """
    return Err(error)


def is_ok(result) -> bool:
    """判断结果是否成功。

    Args:
        result: Result 类型实例

    Returns:
        True 如果是 Ok，False 如果是 Err
    """
    return result.ok


def is_err(result) -> bool:
    """判断结果是否失败。

    Args:
        result: Result 类型实例

    Returns:
        True 如果是 Err，False 如果是 Ok
    """
    return not result.ok


def get_or_throw(result: Ok[T]) -> T:
    """成功取值；失败则抛异常。

    这是「必须处理错误」的函数调用方式：失败时强制抛异常，
    避免忽略错误。

    Args:
        result: Result 类型实例

    Returns:
        成功时的值

    Raises:
        BaseException: 如果 error 本身就是异常对象，直接抛出
        RuntimeError: 如果 error 不是异常对象，包装成 RuntimeError 抛出
    """
    if is_ok(result):
        return result.value
    error = result.error
    if isinstance(error, BaseException):
        raise error
    raise RuntimeError(str(error))


def get_or_undefined(result):
    """成功取值；失败返回 None。

    这是「可选处理错误」的函数调用方式：失败时静默返回 None，
    适用于"有值就用，没值就跳过"的场景。

    Args:
        result: Result 类型实例

    Returns:
        成功时的值，失败时返回 None
    """
    if is_ok(result):
        return result.value
    return None
