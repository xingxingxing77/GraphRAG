"""
管理接口端点。

提供缓存清理、索引重建等管理操作接口。
"""

# --- 第三方库 ---
from fastapi import APIRouter, Depends

# --- 本地模块 ---
from app.api.models import AdminAction
from app.api.deps import get_redis_client
from app.db.redis_client import RedisClient

router = APIRouter()


@router.post("/cache/clear")
async def clear_cache(
    redis: RedisClient = Depends(get_redis_client),
) -> dict[str, str]:
    """清理语义缓存和检索结果缓存。

    Args:
        redis: Redis 客户端。

    Returns:
        操作结果消息。
    """
    # TODO: 清理 Redis 中的 L1 语义缓存和 L2 检索缓存
    raise NotImplementedError


@router.post("/index/rebuild")
async def rebuild_index() -> dict[str, str]:
    """触发索引全量重建。

    Returns:
        操作结果消息。
    """
    # TODO: 调用索引更新器执行全量重建
    raise NotImplementedError


@router.post("/action")
async def execute_admin_action(action: AdminAction) -> dict[str, str]:
    """执行管理操作。

    Args:
        action: 管理操作请求。

    Returns:
        操作结果消息。
    """
    # TODO: 根据 action.action 分发到对应的管理操作
    raise NotImplementedError
