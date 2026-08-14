"""重试退避（对应 pi 的 retry.ts / provider-retry.ts）。

指数退避 + 随机抖动：把可重试的失败（网络错误 / 超时 / 429 / 5xx）自动重试，
避免瞬时故障直接失败。这是「先原理后框架」的手写版。
"""
import asyncio
import random
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass
class RetryConfig:
    max_retries: int = 3       # 最多重试次数（不含首次）
    base_delay: float = 1.0    # 首次退避基准（秒）
    max_delay: float = 30.0    # 退避上限（秒）
    jitter: float = 0.3        # 抖动比例（±30%）


def backoff_delay(attempt: int, config: RetryConfig) -> float:
    """第 attempt 次重试的退避时长（秒）：指数增长 + 随机抖动。"""
    exp = min(config.base_delay * (2 ** attempt), config.max_delay)
    jitter = random.uniform(-config.jitter, config.jitter) * exp
    return max(0.0, exp + jitter)


async def with_retry(
    fn: Callable[[], Awaitable[Any]],
    *,
    config: RetryConfig | None = None,
    should_retry: Callable[[Exception], bool] | None = None,
) -> Any:
    """包装异步函数，失败时按指数退避重试。

    should_retry 判断哪些异常可重试；不传则任何异常都不重试（直接抛）。
    重试耗尽后抛出最后一次异常。
    """
    cfg = config or RetryConfig()
    for attempt in range(cfg.max_retries + 1):
        try:
            return await fn()
        except Exception as exc:
            if attempt >= cfg.max_retries or not (should_retry and should_retry(exc)):
                raise
            await asyncio.sleep(backoff_delay(attempt, cfg))
