"""
短期对话记忆。

管理多轮对话上下文，使用 Redis List 实现滑动窗口。
"""

# --- 标准库 ---
import json
from typing import Optional

# --- 本地模块 ---
from app.db.redis_client import RedisClient


class ConversationMemory:
    """短期对话记忆。

    使用 Redis List 存储最近 N 轮对话，采用滑动窗口策略。

    Attributes:
        redis: Redis 客户端。
        max_turns: 最大保留对话轮数。
    """

    def __init__(self, redis: RedisClient, max_turns: int = 10) -> None:
        """初始化对话记忆。

        Args:
            redis: Redis 客户端实例。
            max_turns: 最大保留对话轮数。
        """
        self.redis = redis
        self.max_turns = max_turns

    async def add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        """添加一轮对话。

        Args:
            session_id: 会话 ID。
            role: 角色（user / assistant）。
            content: 对话内容。
        """
        # TODO: 序列化并推入 Redis List
        # TODO: 如果超过 max_turns，裁剪旧记录
        raise NotImplementedError

    async def get_history(
        self,
        session_id: str,
        last_n: Optional[int] = None,
    ) -> list[dict[str, str]]:
        """获取对话历史。

        Args:
            session_id: 会话 ID。
            last_n: 获取最近 N 轮，None 表示全部。

        Returns:
            对话记录列表 [{"role": "user", "content": "..."}, ...]。
        """
        # TODO: 从 Redis List 获取并反序列化
        raise NotImplementedError

    async def clear(self, session_id: str) -> None:
        """清空会话历史。

        Args:
            session_id: 会话 ID。
        """
        # TODO: 删除 Redis 中的会话 key
        raise NotImplementedError
