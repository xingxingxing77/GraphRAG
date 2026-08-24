"""
短期工作记忆（单元 8.1，J17，04 §4 `wm:{session_id}`）。

使用 Redis List 实现滑动窗口：每轮 QA 以 JSON `{"q","a","ts"}`
LPUSH 入表头，LTRIM 裁剪至 max_turns，EXPIRE 7d 兜底过期
（04 §4：滑动窗口裁剪由应用层 LPUSH+LTRIM 维护）。
注入发生在查询改写之前（架构 L9）；删除会话时经 clear()
级联清理（07 A-05）。
"""

# --- 标准库 ---
import json
import time
from typing import Any

# --- 本地模块 ---
from app.db.redis_client import RedisClient

# 工作记忆 TTL（04 §4：7d）
WM_TTL_SECONDS = 7 * 24 * 3600


class WorkingMemory:
    """短期工作记忆管理器（架构 L9 文件清单命名：working_memory.py）。

    使用 Redis List 存储最近 N 轮对话（Key=`wm:{session_id}`，
    04 §4 唯一命名出处），LPUSH+LTRIM 滑动窗口 + EXPIRE 兜底。

    Attributes:
        redis: Redis 客户端。
        max_turns: 滑动窗口保留的最大轮数。
    """

    def __init__(
        self,
        redis: RedisClient,
        max_turns: int = 10,
        ttl_seconds: int = WM_TTL_SECONDS,
    ) -> None:
        """初始化工作记忆。

        Args:
            redis: Redis 客户端实例。
            max_turns: 最大保留对话轮数（LTRIM 窗口宽度）。
            ttl_seconds: Key 过期时间（04 §4 默认 7d，可经 reliability.yaml 覆盖）。
        """
        self.redis = redis
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _key(session_id: str) -> str:
        """生成 Redis Key（04 §4 命名同源）。

        Args:
            session_id: 会话 ID。

        Returns:
            Key 字符串 `wm:{session_id}`。
        """
        return f"wm:{session_id}"

    async def add_exchange(self, session_id: str, question: str, answer: str) -> None:
        """记录一轮完整问答（写侧尾节点调用，05 §5.4 幂等三件事之一）。

        LPUSH 入表头 → LTRIM 裁剪窗口 → EXPIRE 刷新 TTL。

        Args:
            session_id: 会话 ID。
            question: 用户问题（改写前原始查询）。
            answer: 助手答案终稿。
        """
        entry = json.dumps(
            {"q": question, "a": answer, "ts": int(time.time())},
            ensure_ascii=False,
        )
        key = self._key(session_id)
        await self.redis.lpush(key, entry)
        await self.redis.ltrim(key, 0, self.max_turns - 1)
        await self.redis.expire(key, self.ttl_seconds)

    async def get_history(
        self,
        session_id: str,
        last_n: int | None = None,
    ) -> list[dict[str, Any]]:
        """获取对话历史（注入节点调用，置于改写前）。

        Args:
            session_id: 会话 ID。
            last_n: 取最近 N 轮；None 表示窗口内全部。

        Returns:
            轮次列表（旧→新排序），每项 {"q","a","ts"}。
        """
        end = -1 if last_n is None else last_n - 1
        raw = await self.redis.lrange(self._key(session_id), 0, end)
        entries = [json.loads(item) for item in raw]
        entries.reverse()  # LPUSH 表头为最新，翻转为旧→新
        return entries

    async def clear(self, session_id: str) -> None:
        """清空会话工作记忆（DELETE /sessions 级联，07 A-05）。

        Args:
            session_id: 会话 ID。
        """
        await self.redis.delete(self._key(session_id))
