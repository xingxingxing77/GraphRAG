"""
依赖注入工厂。

使用 FastAPI 的 Depends 机制管理数据库客户端和 Agent 实例的生命周期。
"""

# --- 标准库 ---
from functools import lru_cache
from pathlib import Path
from typing import AsyncGenerator

# --- 第三方库 ---
from langgraph.graph.state import CompiledStateGraph

# --- 本地模块 ---
from app.core.config import AppSettings, get_settings
from app.db.neo4j_client import Neo4jClient
from app.db.qdrant_client import QdrantDBClient
from app.db.redis_client import RedisClient
from app.embedding.base import EmbeddingService
from app.embedding.ollama_client import OllamaClient
from app.embedding.service import BgeM3EmbeddingService
from app.pipeline.config import load_pipeline_config
from app.pipeline.ingestion.manifest import JsonFileManifestStore
from app.pipeline.ingestion.service import IngestionService

_REPO_ROOT = Path(__file__).resolve().parents[2]


async def get_neo4j_client() -> AsyncGenerator[Neo4jClient, None]:
    """获取 Neo4j 客户端实例（依赖注入，单例复用驱动）。

    Yields:
        Neo4jClient: 已连接的 Neo4j 客户端。
    """
    global _neo4j_client
    if _neo4j_client is None:
        settings = get_settings()
        _neo4j_client = Neo4jClient(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
        )
    yield _neo4j_client


_neo4j_client: Neo4jClient | None = None


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
    """获取 Embedding 服务单例（依赖注入，单元 2.3）。

    开发默认仅接 dense 通道（Ollama）；FlagEmbedding 随
    pipeline 可选组安装后经 flag_client 接入 sparse 通道。

    Returns:
        EmbeddingService: BGE-M3 Embedding 服务。
    """
    global _embedding_service
    if _embedding_service is None:
        settings = get_settings()
        ollama_client = OllamaClient(base_url=settings.ollama_base_url)
        _embedding_service = BgeM3EmbeddingService(
            ollama_client=ollama_client,
            model_name=settings.embedding_model,
            flag_client=None,  # TODO(阶段 3): FlagEmbedding 安装后接入 sparse 通道
        )
    return _embedding_service


_embedding_service: BgeM3EmbeddingService | None = None


async def get_agent() -> CompiledStateGraph:
    """获取编译后的 LangGraph Agent 实例（依赖注入）。

    Returns:
        CompiledStateGraph: 编译后的 Agent 状态图。
    """
    # TODO: 返回 Agent 单例
    raise NotImplementedError


_ingestion_service: IngestionService | None = None


def get_ingestion_service() -> IngestionService:
    """获取采集编排器单例（单元 1.1）。

    开发默认用 JsonFileManifestStore；生产接 PostgresManifestStore
    （04 §2.3 doc_documents SSOT，随阶段 2/3 接线）。

    Returns:
        IngestionService: 采集编排器。
    """
    global _ingestion_service
    if _ingestion_service is None:
        cfg = load_pipeline_config()
        manifest = JsonFileManifestStore(_REPO_ROOT / "data" / "ingest_manifest.json")
        _ingestion_service = IngestionService(
            manifest=manifest,
            config=cfg.pipeline.ingestion,
            base_dir=_REPO_ROOT,
        )
    return _ingestion_service
