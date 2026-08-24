"""
Redis 客户端封装（04 §4 · 单元 3.2 扩展死信队列）。

封装 redis.asyncio 的连接管理与通用操作：缓存（get/set/ttl）、
Hash（画像）、List（工作记忆 LPUSH+LTRIM / 死信队列）、健康检查。
Key 命名以 04 §4 为权威（wm:{session_id} / user:{id}:profile /
l2:ret:{norm_hash} / rl:{principal}:{minute}）。
"""

# --- 标准库 ---
from typing import Any, Optional

# --- 第三方库 ---
from redis.asyncio import Redis

# ES 同步死信队列 Key（11 D9：失败入 Redis List，admin 可重放）
ES_DEAD_LETTER_KEY = "es:dead_letter"


class RedisClient:
    """Redis 异步客户端封装。

    Attributes:
        host: Redis 服务地址。
        port: Redis 端口。
        db: Redis DB 编号。
    """

    def __init__(self, host: str, port: int, db: int = 0) -> None:
        """初始化 Redis 客户端。

        Args:
            host: Redis 服务地址。
            port: Redis 端口。
            db: Redis DB 编号。
        """
        self.host = host
        self.port = port
        self.db = db
        self._client: Optional[Redis] = None

    async def connect(self) -> None:
        """建立 Redis 异步连接。"""
        if self._client is None:
            self._client = Redis(
                host=self.host, port=self.port, db=self.db, decode_responses=True
            )

    async def close(self) -> None:
        """关闭 Redis 连接。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _ensure_client(self) -> Redis:
        """确保连接已建立。

        Returns:
            Redis 实例。
        """
        if self._client is None:
            await self.connect()
        assert self._client is not None
        return self._client

    async def get(self, key: str) -> Optional[str]:
        """获取缓存值。

        Args:
            key: 缓存键。

        Returns:
            缓存值，不存在时返回 None。
        """
        client = await self._ensure_client()
        result = await client.get(key)
        if result is None:
            return None
        return result.decode("utf-8") if isinstance(result, bytes) else str(result)

    async def set(
        self,
        key: str,
        value: str,
        ttl: Optional[int] = None,
    ) -> None:
        """设置缓存值。

        Args:
            key: 缓存键。
            value: 缓存值。
            ttl: 过期时间（秒），None 表示不过期。
        """
        client = await self._ensure_client()
        if ttl is not None:
            await client.set(key, value, ex=ttl)
        else:
            await client.set(key, value)

    async def delete(self, key: str) -> None:
        """删除缓存键。

        Args:
            key: 要删除的缓存键。
        """
        client = await self._ensure_client()
        await client.delete(key)

    async def hgetall(self, name: str) -> dict[str, str]:
        """获取 Hash 所有字段和值。

        Args:
            name: Hash 键名。

        Returns:
            字段-值字典。
        """
        client = await self._ensure_client()
        result = await client.hgetall(name)
        return {str(k): str(v) for k, v in result.items()}

    async def hset(self, name: str, key: str, value: str) -> None:
        """设置 Hash 字段值。

        Args:
            name: Hash 键名。
            key: 字段名。
            value: 字段值。
        """
        client = await self._ensure_client()
        await client.hset(name, key, value)

    async def lpush(self, name: str, *values: str) -> None:
        """从列表左端推入元素。

        Args:
            name: 列表键名。
            *values: 要推入的值。
        """
        client = await self._ensure_client()
        await client.lpush(name, *values)

    async def lrange(self, name: str, start: int, end: int) -> list[str]:
        """获取列表指定范围元素。

        Args:
            name: 列表键名。
            start: 起始索引。
            end: 结束索引。

        Returns:
            元素列表。
        """
        client = await self._ensure_client()
        result = await client.lrange(name, start, end)
        return [str(v) for v in result]

    async def ltrim(self, name: str, start: int, end: int) -> None:
        """裁剪列表到指定范围（工作记忆滑动窗口，04 §4）。

        Args:
            name: 列表键名。
            start: 起始索引。
            end: 结束索引。
        """
        client = await self._ensure_client()
        await client.ltrim(name, start, end)

    async def rpop(self, name: str) -> Optional[str]:
        """从列表右端弹出一个元素（死信重放消费）。

        Args:
            name: 列表键名。

        Returns:
            弹出的元素，空列表返回 None。
        """
        client = await self._ensure_client()
        result = await client.rpop(name)
        if result is None:
            return None
        return result.decode("utf-8") if isinstance(result, bytes) else str(result)

    async def llen(self, name: str) -> int:
        """获取列表长度。

        Args:
            name: 列表键名。

        Returns:
            列表长度。
        """
        client = await self._ensure_client()
        return int(await client.llen(name))

    async def expire(self, key: str, ttl: int) -> None:
        """为键设置过期时间。

        Args:
            key: 键名。
            ttl: 过期时间（秒）。
        """
        client = await self._ensure_client()
        await client.expire(key, ttl)

    async def dead_letter_push(self, message: str) -> None:
        """推入 ES 同步死信队列（11 D9）。

        Args:
            message: 失败消息（JSON 序列化的同步任务）。
        """
        await self.lpush(ES_DEAD_LETTER_KEY, message)

    async def dead_letter_pop(self) -> Optional[str]:
        """弹出一条死信消息（重放消费，FIFO）。

        Returns:
            死信消息，队列为空返回 None。
        """
        return await self.rpop(ES_DEAD_LETTER_KEY)

    async def dead_letter_len(self) -> int:
        """死信队列长度。

        Returns:
            队列中待重放消息数。
        """
        return await self.llen(ES_DEAD_LETTER_KEY)

    async def check_health(self) -> bool:
        """检查 Redis 连接健康状态。

        Returns:
            True 表示连接正常。
        """
        try:
            client = await self._ensure_client()
            return bool(await client.ping())
        except Exception:  # noqa: BLE001 - 健康检查不抛错
            return False
