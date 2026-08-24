"""限流与并发配置测试（单元 9.2 S3，07 §7 配套）。

断言：429 + Retry-After；fail-open（存储故障放行）；窗口键规范
（04 §4 rl:{principal}:{minute}）；并发上限配置读取。
"""

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.api.rate_limit import (
    InMemoryRateLimitStore,
    RateLimiter,
    load_concurrency_config,
)


class FailingStore:
    """故障存储替身（模拟 Redis 不可达）。"""

    async def hit(self, key: str, window_seconds: int) -> int:
        """总是抛异常。"""
        raise RuntimeError("redis down")


class TestRateLimiter:
    """固定窗口限流。"""

    @pytest.mark.asyncio
    async def test_within_limit_allowed(self) -> None:
        limiter = RateLimiter(InMemoryRateLimitStore(), max_requests=3, window_seconds=60)
        for _ in range(3):
            allowed, retry_after = await limiter.check("user-1")
            assert allowed is True
            assert retry_after == 0

    @pytest.mark.asyncio
    async def test_over_limit_returns_retry_after(self) -> None:
        limiter = RateLimiter(InMemoryRateLimitStore(), max_requests=2, window_seconds=60)
        await limiter.check("user-1")
        await limiter.check("user-1")
        allowed, retry_after = await limiter.check("user-1")
        assert allowed is False
        assert 1 <= retry_after <= 60  # Retry-After 为窗口剩余秒数

    @pytest.mark.asyncio
    async def test_principals_isolated(self) -> None:
        limiter = RateLimiter(InMemoryRateLimitStore(), max_requests=1, window_seconds=60)
        assert (await limiter.check("user-1"))[0] is True
        assert (await limiter.check("user-2"))[0] is True  # 不同主体互不影响
        assert (await limiter.check("user-1"))[0] is False

    @pytest.mark.asyncio
    async def test_fail_open_on_store_failure(self) -> None:
        """存储故障 fail-open（D5：限流不阻塞主链路）。"""
        limiter = RateLimiter(FailingStore(), max_requests=1, window_seconds=60)
        allowed, retry_after = await limiter.check("user-1")
        assert allowed is True
        assert retry_after == 0

    def test_window_key_format(self) -> None:
        key = RateLimiter.window_key("user-42")
        assert key.startswith("rl:user-42:")  # 04 §4 键规范


class TestConcurrencyConfig:
    """D6 并发上限配置读取。"""

    def test_loads_reliability_yaml(self) -> None:
        cfg = load_concurrency_config()
        assert cfg["local_llm_semaphore"] == 1  # Profile B 本地串行
        assert cfg["cloud_llm_semaphore"] == 4
        assert cfg["reranker_semaphore"] == 1
        assert cfg["retrieval_gather_timeout_s"] == 6
