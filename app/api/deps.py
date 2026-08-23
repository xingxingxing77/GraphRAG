"""
依赖注入工厂。

使用 FastAPI 的 Depends 机制管理数据库客户端和 Agent 实例的生命周期。
"""

# --- 标准库 ---
from functools import lru_cache
from typing import AsyncGenerator

# --- 第三方库 ---
from langgraph.graph.state import CompiledStateGraph

# --- 本地模块 ---
from app.core.config import AppSettings, get_settings
from app.db.neo4j_client import Neo4jClient
from app.db.qdrant_client import QdrantDBClient
from app.db.redis_client import RedisClient
from app.embedding.service import EmbeddingService


async def get_neo4j_client() -> AsyncGenerator[Neo4jClient, None]:
    """获取 Neo4j 客户端实例（依赖注入）。

    Yields:
        Neo4jClient: 已连接的 Neo4j 客户端。
    """
    # TODO: 创建并 yield Neo4j 客户端，确保关闭
    raise NotImplementedError


async def get_qdrant_client() -> AsyncGenerator[QdrantDBClient, None]:
    """获取 Qdrant 客户端实例（依赖注入）。

    Yields:
        QdrantDBClient: 已连接的 Qdrant 客户端。
    """
    # TODO: 创建并 yield Qdrant 客户端，确保关闭
    raise NotImplementedError


async def get_redis_client() -> AsyncGenerator[RedisClient, None]:
    """获取 Redis 客户端实例（依赖注入）。

    Yields:
        RedisClient: 已连接的 Redis 客户端。
    """
    # TODO: 创建并 yield Redis 客户端，确保关闭
    raise NotImplementedError


async def get_embedding_service() -> EmbeddingService:
    """获取 Embedding 服务实例（依赖注入）。

    Returns:
        EmbeddingService: BGE-M3 Embedding 服务。
    """
    # TODO: 返回 EmbeddingService 单例
    raise NotImplementedError


async def get_agent() -> CompiledStateGraph:
    """获取编译后的 LangGraph Agent 实例（依赖注入）。

    Returns:
        CompiledStateGraph: 编译后的 Agent 状态图。
    """
    # TODO: 返回 Agent 单例
    raise NotImplementedError
