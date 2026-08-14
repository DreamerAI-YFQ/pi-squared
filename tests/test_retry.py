import asyncio

from pi_agent.providers.openai import HTTPError, _should_retry
from pi_agent.streaming.retry import RetryConfig, backoff_delay, with_retry


def test_backoff_delay_grows_exponentially():
    cfg = RetryConfig(base_delay=1.0, max_delay=30.0, jitter=0.0)
    assert backoff_delay(0, cfg) == 1.0
    assert backoff_delay(1, cfg) == 2.0
    assert backoff_delay(2, cfg) == 4.0
    assert backoff_delay(3, cfg) == 8.0


def test_backoff_delay_capped():
    cfg = RetryConfig(base_delay=10.0, max_delay=25.0, jitter=0.0)
    assert backoff_delay(2, cfg) == 25.0  # 10*4=40 被上限 25 截断


def test_with_retry_succeeds_first_try():
    calls = 0

    async def fn():
        nonlocal calls
        calls += 1
        return "ok"

    assert asyncio.run(with_retry(fn, config=RetryConfig(max_retries=3))) == "ok"
    assert calls == 1


def test_with_retry_retries_then_succeeds():
    calls = 0

    async def fn():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("临时失败")
        return "ok"

    result = asyncio.run(with_retry(
        fn,
        config=RetryConfig(max_retries=3, base_delay=0.0),
        should_retry=lambda e: True,
    ))
    assert result == "ok"
    assert calls == 3


def test_with_retry_non_retryable_raises_immediately():
    calls = 0

    async def fn():
        nonlocal calls
        calls += 1
        raise ValueError("不可重试")

    try:
        asyncio.run(with_retry(fn, config=RetryConfig(max_retries=3), should_retry=lambda e: False))
        assert False, "应当抛出"
    except ValueError:
        pass
    assert calls == 1


def test_with_retry_exhausts():
    calls = 0

    async def fn():
        nonlocal calls
        calls += 1
        raise RuntimeError("一直失败")

    try:
        asyncio.run(with_retry(
            fn,
            config=RetryConfig(max_retries=2, base_delay=0.0),
            should_retry=lambda e: True,
        ))
        assert False, "应当抛出"
    except RuntimeError:
        pass
    assert calls == 3  # 首次 + 2 次重试


def test_should_retry_status_codes():
    assert _should_retry(HTTPError(429, "")) is True
    assert _should_retry(HTTPError(503, "")) is True
    assert _should_retry(HTTPError(400, "")) is False
    assert _should_retry(HTTPError(404, "")) is False
