"""
长期用户画像（单元 8.2，04 §4 `user:{user_id}:profile` / `:summaries`）。

存储结构（04 §4 唯一命名出处）：
- `user:{id}:profile` Hash：preferences(JSON) · summary · updated_at，
  无 TTL，随用户生命周期；
- `user:{id}:summaries` List：历史交互摘要（LPUSH+LTRIM 20 封顶），
  作为蒸馏源，由 distill() 定期合并进 profile.summary
  （11 路线图 Phase 4：画像 Hash 无 TTL + summaries LTRIM 20 + 定期蒸馏）。
"""

# --- 标准库 ---
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

# --- 本地模块 ---
from app.db.redis_client import RedisClient

# summaries 蒸馏源 List 封顶条数（11 路线图 Phase 4）
SUMMARIES_CAP = 20

# 蒸馏函数签名：输入摘要列表，输出合并后的画像摘要文本
SummaryFn = Callable[[list[str]], Awaitable[str]]


class UserProfile:
    """长期用户画像管理器。

    Attributes:
        redis: Redis 客户端。
        summarizer: 蒸馏函数（extractor 角色 LLM 封装；None 时不可蒸馏）。
    """

    def __init__(self, redis: RedisClient, summarizer: SummaryFn | None = None) -> None:
        """初始化用户画像管理器。

        Args:
            redis: Redis 客户端实例。
            summarizer: 可选蒸馏函数；真实部署注入 extractor 角色
                LLM 调用（依赖 app.llm client.chat 落地），单测注入替身。
        """
        self.redis = redis
        self.summarizer = summarizer

    @staticmethod
    def _profile_key(user_id: str) -> str:
        """画像 Hash Key（04 §4）。"""
        return f"user:{user_id}:profile"

    @staticmethod
    def _summaries_key(user_id: str) -> str:
        """蒸馏源 List Key（04 §4 v1.1）。"""
        return f"user:{user_id}:summaries"

    async def get_profile(self, user_id: str) -> dict[str, Any]:
        """获取用户画像。

        Args:
            user_id: 用户 ID。

        Returns:
            {"preferences": dict, "summary": str, "updated_at": str|None}。
            无记录时返回空偏好与空摘要的默认结构。
        """
        raw = await self.redis.hgetall(self._profile_key(user_id))
        if not raw:
            return {"preferences": {}, "summary": "", "updated_at": None}
        try:
            preferences = json.loads(raw.get("preferences", "{}"))
        except json.JSONDecodeError:
            preferences = {}
        return {
            "preferences": preferences,
            "summary": raw.get("summary", ""),
            "updated_at": raw.get("updated_at"),
        }

    async def update_preferences(self, user_id: str, preferences: dict[str, Any]) -> None:
        """整体覆盖式更新偏好字段并刷新 updated_at。

        Args:
            user_id: 用户 ID。
            preferences: 偏好字典（整体写入 Hash 的 preferences 字段）。
        """
        await self._write_profile_fields(
            user_id,
            {"preferences": json.dumps(preferences, ensure_ascii=False)},
        )

    async def add_summary(self, user_id: str, summary: str) -> None:
        """追加一条交互摘要到蒸馏源 List（LTRIM 20 封顶）。

        Args:
            user_id: 用户 ID。
            summary: 单轮/话题段交互摘要文本。
        """
        key = self._summaries_key(user_id)
        await self.redis.lpush(key, summary)
        await self.redis.ltrim(key, 0, SUMMARIES_CAP - 1)

    async def get_summaries(self, user_id: str) -> list[str]:
        """读取蒸馏源摘要列表（旧→新）。

        Args:
            user_id: 用户 ID。

        Returns:
            摘要文本列表。
        """
        raw = await self.redis.lrange(self._summaries_key(user_id), 0, -1)
        return list(reversed(raw))

    async def distill(self, user_id: str) -> str:
        """将蒸馏源摘要合并进 profile.summary（定期任务调用）。

        优先使用注入的 summarizer（extractor 角色）；未注入时退化为
        截断拼接（保证无 LLM 环境下画像仍可推进），并在结果中体现。

        Args:
            user_id: 用户 ID。

        Returns:
            合并后的画像摘要文本。

        Raises:
            RuntimeError: 蒸馏源为空或 summarizer 执行失败时向上传播。
        """
        summaries = await self.get_summaries(user_id)
        if not summaries:
            current = await self.get_profile(user_id)
            return str(current.get("summary", ""))
        if self.summarizer is not None:
            merged = await self.summarizer(summaries)
        else:
            joined = "\n".join(summaries)
            merged = joined[:2000]
        await self._write_profile_fields(user_id, {"summary": merged})
        return merged

    async def _write_profile_fields(self, user_id: str, fields: dict[str, str]) -> None:
        """写入 Hash 字段并统一刷新 updated_at（ISO8601 UTC）。"""
        name = self._profile_key(user_id)
        for field, value in fields.items():
            await self.redis.hset(name, field, value)
        await self.redis.hset(
            name, "updated_at", datetime.now(UTC).isoformat()
        )
