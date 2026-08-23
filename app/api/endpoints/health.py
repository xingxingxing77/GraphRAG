"""
健康检查端点。

提供 /health 和 /ready 接口，检测各服务连通性。
"""

# --- 第三方库 ---
from fastapi import APIRouter, Depends

# --- 本地模块 ---
from app.api.models import HealthStatus
from app.api.deps import get_neo4j_client, get_qdrant_client, get_redis_client
from app.db.neo4j_client import Neo4jClient
from app.db.qdrant_client import QdrantDBClient
from app.db.redis_client import RedisClient

router = APIRouter()


@router.get("/health", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """基础健康检查。

    Returns:
        HealthStatus: 各服务连接状态。
    """
    # TODO: 返回静态的 ok 状态
    raise NotImplementedError


@router.get("/ready", response_model=HealthStatus)
async def readiness_check(
    neo4j: Neo4jClient = Depends(get_neo4j_client),
    qdrant: QdrantDBClient = Depends(get_qdrant_client),
    redis: RedisClient = Depends(get_redis_client),
) -> HealthStatus:
    """就绪检查，验证所有依赖服务的连通性。

    Args:
        neo4j: Neo4j 客户端。
        qdrant: Qdrant 客户端。
        redis: Redis 客户端。

    Returns:
        HealthStatus: 各服务实际连通状态。
    """
    # TODO: 分别检查 Neo4j、Qdrant、Redis、Ollama 的健康状态
    # TODO: 汇总结果返回 HealthStatus
    raise NotImplementedError
