"""
依赖注入工厂。

使用 FastAPI 的 Depends 机制管理数据库客户端和 Agent 实例的生命周期。
"""

# --- 标准库 ---
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncGenerator

# --- 第三方库 ---
from langgraph.graph.state import CompiledStateGraph

# --- 本地模块 ---
from app.core.config import AppSettings, get_settings
from app.db.neo4j_client import Neo4jClient
from app.db.es_client import ESClient
from app.db.qdrant_client import QdrantDBClient
from app.db.redis_client import RedisClient
from app.embedding.base import EmbeddingService
from app.embedding.ollama_client import OllamaClient
from app.embedding.service import BgeM3EmbeddingService
from app.memory.conversation import ConversationMemory
from app.memory.episodic import EpisodicMemory
from app.memory.scheduler import MemoryScheduler
from app.memory.semantic_cache import SemanticCache
from app.pipeline.config import load_pipeline_config
from app.pipeline.ingestion.manifest import JsonFileManifestStore
from app.pipeline.ingestion.service import IngestionService
from app.reranking.reranker import BGEReranker

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
    """获取 Qdrant 客户端实例（依赖注入，单例复用）。

    Yields:
        QdrantDBClient: 已配置的 Qdrant 客户端。
    """
    global _qdrant_client
    if _qdrant_client is None:
        settings = get_settings()
        _qdrant_client = QdrantDBClient(
            host=settings.qdrant_host, port=settings.qdrant_port
        )
    yield _qdrant_client


_qdrant_client: QdrantDBClient | None = None


async def get_es_client() -> AsyncGenerator[ESClient, None]:
    """获取 ES 客户端实例（依赖注入，单例复用）。

    Yields:
        ESClient: 已配置的 ES 客户端。
    """
    global _es_client
    if _es_client is None:
        settings = get_settings()
        _es_client = ESClient(host=settings.elasticsearch_host)
    yield _es_client


_es_client: ESClient | None = None


async def get_reranker() -> AsyncGenerator[BGEReranker, None]:
    """获取 Reranker 单例（依赖注入，模型惰性加载复用）。

    Yields:
        BGEReranker: 精排器实例。
    """
    global _reranker
    if _reranker is None:
        _reranker = BGEReranker()
    yield _reranker


_reranker: BGEReranker | None = None


async def get_redis_client() -> AsyncGenerator[RedisClient, None]:
    """获取 Redis 客户端实例（依赖注入，单例复用连接）。

    Yields:
        RedisClient: 已配置的 Redis 客户端（首用时建立连接）。
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = RedisClient(
            host=settings.redis_host, port=settings.redis_port, db=settings.redis_db
        )
    yield _redis_client


_redis_client: RedisClient | None = None


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


async def get_agent() -> "CompiledStateGraph[Any]":
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


# ============================================================
# 记忆层服务栈（单元 8.1-8.3）
# ============================================================


class MemoryStack:
    """记忆层组件聚合（图节点经 get_memory_stack 惰性获取）。

    Attributes:
        redis: Redis 客户端。
        qdrant: Qdrant 客户端。
        conversation: 工作记忆。
        episodic: 情景记忆。
        scheduler: 注入调度器。
        semantic_cache: 语义缓存（L1 ANN + L2 Redis）。
    """

    def __init__(
        self,
        redis: RedisClient,
        qdrant: QdrantDBClient,
        conversation: "ConversationMemory",
        episodic: "EpisodicMemory",
        scheduler: "MemoryScheduler",
        semantic_cache: "SemanticCache",
    ) -> None:
        self.redis = redis
        self.qdrant = qdrant
        self.conversation = conversation
        self.episodic = episodic
        self.scheduler = scheduler
        self.semantic_cache = semantic_cache


_memory_stack: MemoryStack | None = None


async def get_memory_stack() -> MemoryStack:
    """获取记忆层服务栈单例（客户端连接均首用时惰性建立）。

    Returns:
        MemoryStack: 组装完成的记忆层组件集合。
    """
    global _memory_stack
    if _memory_stack is None:
        settings = get_settings()
        redis = RedisClient(
            host=settings.redis_host, port=settings.redis_port, db=settings.redis_db
        )
        qdrant = QdrantDBClient(host=settings.qdrant_host, port=settings.qdrant_port)
        embedder = await get_embedding_service()
        conversation = ConversationMemory(redis)
        episodic = EpisodicMemory(qdrant, embedder)
        scheduler = MemoryScheduler(conversation, episodic, embedder)
        semantic_cache = SemanticCache(
            qdrant=qdrant, embedder=embedder, redis=redis
        )
        _memory_stack = MemoryStack(
            redis=redis,
            qdrant=qdrant,
            conversation=conversation,
            episodic=episodic,
            scheduler=scheduler,
            semantic_cache=semantic_cache,
        )
    return _memory_stack


async def get_semantic_cache() -> AsyncGenerator[SemanticCache, None]:
    """获取语义缓存单例（precheck 端点依赖注入入口）。

    Yields:
        SemanticCache: L1 ANN + L2 Redis 语义缓存。
    """
    stack = await get_memory_stack()
    yield stack.semantic_cache
