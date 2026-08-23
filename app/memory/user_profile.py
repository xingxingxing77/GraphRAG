"""
长期用户画像。

存储用户偏好和历史摘要，使用 Redis Hash 结构。
"""

# --- 标准库 ---
import json
from typing import Any, Optional

# --- 本地模块 ---
from app.db.redis_client import RedisClient


class UserProfile:
    """长期用户画像管理器。

    使用 Redis Hash 存储用户的偏好设置和历史交互摘要。
    Key 格式: ``user:{user_id}:profile``
    """

    def __init__(self, redis: RedisClient) -> None:
        """初始化用户画像管理器。

        Args:
            redis: Redis 客户端实例。
        """
        self.redis = redis

    def _key(self, user_id: str) -> str:
        """生成 Redis Key。

        Args:
            user_id: 用户 ID。

        Returns:
            Redis Key 字符串。
        """
        return f"user:{user_id}:profile"

    async def get_profile(self, user_id: str) -> dict[str, Any]:
        """获取用户画像。

        Args:
            user_id: 用户 ID。

        Returns:
            用户画像字典，包含 preferences 和 past_summaries。
        """
        # TODO: 从 Redis Hash 读取并反序列化
        raise NotImplementedError

    async def update_profile(
        self,
        user_id: str,
        updates: dict[str, Any],
    ) -> None:
        """更新用户画像。

        Args:
            user_id: 用户 ID。
            updates: 要更新的字段。
        """
        # TODO: 合并更新并写入 Redis Hash
        raise NotImplementedError

    async def add_summary(self, user_id: str, summary: str) -> None:
        """添加历史交互摘要。

        Args:
            user_id: 用户 ID。
            summary: 交互摘要文本。
        """
        # TODO: 追加到 past_summaries 列表
        raise NotImplementedError
