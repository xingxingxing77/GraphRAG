"""
限流与并发控制（架构 §6.3 D6 · 单元 9.2）。

- 固定窗口计数限流：Redis `rl:{principal}:{minute}` 键（04 §4），
  超限返回 429 + Retry-After 头（02 §6 AUTH_429_RATE_LIMITED）；
- Redis 不可达 fail-open（D5：限流故障不阻塞主链路）；
- 全局 semaphore 上限经 reliability.yaml concurrency 段驱动（D6）。
"""

# --- 标准库 ---
import logging
import time
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "reliability.yaml"

# 默认限流参数（对齐 02 §6：兑换/请求限流）
DEFAULT_MAX_REQUESTS = 60
DEFAULT_WINDOW_SECONDS = 60


class RateLimitStore(Protocol):
    """限流计数器存储协议（Redis 实现 / 内存测试实现）。"""

    async def hit(self, key: str, window_seconds: int) -> int:
        """记录一次命中并返回窗口内累计次数。

        Args:
            key: 限流键（rl:{principal}:{minute}）。
            window_seconds: 窗口长度（用于键过期）。

        Returns:
            窗口内累计次数。
        """
        ...


class InMemoryRateLimitStore:
    """内存限流存储（单测/Redis 不可达降级用）。"""

    def __init__(self) -> None:
        """初始化空计数表。"""
        self._counts: dict[str, tuple[int, float]] = {}

    async def hit(self, key: str, window_seconds: int) -> int:
        """记录命中（过期键自动清零）。

        Args:
            key: 限流键。
            window_seconds: 窗口长度。

        Returns:
            窗口内累计次数。
        """
        now = time.time()
        count, expires_at = self._counts.get(key, (0, 0.0))
        if now >= expires_at:
            count = 0
        count += 1
        self._counts[key] = (count, now + window_seconds)
        return count


class RedisRateLimitStore:
    """Redis 限流存储（INCR + EXPIRE 原子窗口，04 §4 键规范）。"""

    def __init__(self, redis_client: Any) -> None:
        """初始化存储。

        Args:
            redis_client: RedisClient 实例（内部 redis.asyncio 客户端可直达）。
        """
        self._redis = redis_client

    async def hit(self, key: str, window_seconds: int) -> int:
        """INCR 计数并设置窗口过期。

        Args:
            key: 限流键。
            window_seconds: 窗口长度。

        Returns:
            窗口内累计次数。

        Raises:
            Exception: Redis 不可达（由限流器 fail-open 处理）。
        """
        inner = await self._redis._ensure_client()
        count = await inner.incr(key)
        if count == 1:
            await inner.expire(key, window_seconds)
        return int(count)


class RateLimiter:
    """固定窗口限流器（429 + Retry-After）。

    Attributes:
        max_requests: 窗口内最大请求数。
        window_seconds: 窗口长度（秒）。
    """

    def __init__(
        self,
        store: RateLimitStore,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> None:
        """初始化限流器。

        Args:
            store: 计数存储。
            max_requests: 窗口内最大请求数。
            window_seconds: 窗口长度（秒）。
        """
        self.store = store
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    @staticmethod
    def window_key(principal: str) -> str:
        """构造分钟窗口键（04 §4：rl:{principal}:{minute}）。

        Args:
            principal: 主体标识（用户 ID / API Key 指纹 / IP）。

        Returns:
            限流键。
        """
        minute = int(time.time() // 60)
        return f"rl:{principal}:{minute}"

    async def check(self, principal: str) -> tuple[bool, int]:
        """检查主体是否超限。

        fail-open：存储故障时放行（D5，限流不阻塞主链路）。

        Args:
            principal: 主体标识。

        Returns:
            (是否放行, Retry-After 秒数)；放行时 Retry-After 为 0。
        """
        key = self.window_key(principal)
        try:
            count = await self.store.hit(key, self.window_seconds)
        except Exception as exc:  # noqa: BLE001 - fail-open
            logger.warning("限流存储故障，fail-open 放行: %s", exc)
            return True, 0
        if count <= self.max_requests:
            return True, 0
        # 窗口剩余秒数作为 Retry-After
        elapsed_in_window = int(time.time() % self.window_seconds)
        retry_after = max(1, self.window_seconds - elapsed_in_window)
        return False, retry_after


def load_concurrency_config() -> dict[str, int]:
    """读取 reliability.yaml concurrency 段（D6 并发上限）。

    Returns:
        {local_llm_semaphore, cloud_llm_semaphore, reranker_semaphore,
        retrieval_gather_timeout_s}；缺失用默认。
    """
    defaults = {
        "local_llm_semaphore": 1,
        "cloud_llm_semaphore": 4,
        "reranker_semaphore": 1,
        "retrieval_gather_timeout_s": 6,
    }
    try:
        import yaml

        with open(_CONFIG_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        section = cfg.get("concurrency") or {}
        return {**defaults, **{k: int(v) for k, v in section.items()}}
    except Exception:  # noqa: BLE001 - 配置缺失用默认
        return defaults
