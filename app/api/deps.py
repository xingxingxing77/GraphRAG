"""
依赖注入工厂。

使用 FastAPI 的 Depends 机制管理数据库客户端和 Agent 实例的生命周期。
"""

# --- 标准库 ---
import asyncio
import logging
import os
from functools import lru_cache
from typing import Any, AsyncGenerator

import yaml

# --- 第三方库 ---

# --- 本地模块 ---
from app.core.config import AppSettings, get_settings
from app.db.neo4j_client import Neo4jClient
from app.db.es_client import ESClient
from app.db.qdrant_client import QdrantDBClient
from app.db.redis_client import RedisClient
from app.embedding.base import EmbeddingService
from app.embedding.flag_client import FlagClient
from app.embedding.ollama_client import OllamaClient
from app.embedding.service import BgeM3EmbeddingService
from app.memory.working_memory import WorkingMemory
from app.memory.episodic import EpisodicMemory
from app.memory.scheduler import MemoryScheduler
from app.memory.semantic_cache import SemanticCache
from app.pipeline.config import load_pipeline_config
from app.pipeline.ingestion.manifest import JsonFileManifestStore
from app.pipeline.ingestion.service import IngestionService
from app.reranking.reranker import BGEReranker

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 并发锁：防止首个并发请求创建多实例覆盖连接池（P0-02）
_neo4j_lock = asyncio.Lock()
_qdrant_lock = asyncio.Lock()
_es_lock = asyncio.Lock()
_reranker_lock = asyncio.Lock()
_redis_lock = asyncio.Lock()


async def get_neo4j_client() -> AsyncGenerator[Neo4jClient, None]:
    """获取 Neo4j 客户端实例（依赖注入，单例复用驱动）。

    Yields:
        Neo4jClient: 已连接的 Neo4j 客户端。
    """
    global _neo4j_client
    if _neo4j_client is None:
        async with _neo4j_lock:
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
        async with _qdrant_lock:
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
        async with _es_lock:
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
        async with _reranker_lock:
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
        async with _redis_lock:
            if _redis_client is None:
                settings = get_settings()
                _redis_client = RedisClient(
                    host=settings.redis_host, port=settings.redis_port, db=settings.redis_db
                )
    yield _redis_client


_redis_client: RedisClient | None = None


_embedding_lock = asyncio.Lock()


async def get_embedding_service() -> EmbeddingService:
    """获取 Embedding 服务单例（依赖注入，单元 2.3）。

    开发默认仅接 dense 通道（Ollama）；FlagEmbedding 随
    pipeline 可选组安装后经 flag_client 接入 sparse 通道。

    Returns:
        EmbeddingService: BGE-M3 Embedding 服务。
    """
    global _embedding_service
    if _embedding_service is None:
        async with _embedding_lock:
            if _embedding_service is None:
                settings = get_settings()
                ollama_client = OllamaClient(base_url=settings.ollama_base_url)
                flag_client: FlagClient | None
                try:
                    flag_client = FlagClient()  # sparse 通道（进程内 BGE-M3，H1/J3）
                except Exception as exc:  # noqa: BLE001 - FlagEmbedding 未装/模型缺失时降级
                    logging.getLogger(__name__).warning("FlagClient 初始化失败，sparse 通道降级: %s", exc)
                    flag_client = None
                _embedding_service = BgeM3EmbeddingService(
                    ollama_client=ollama_client,
                    model_name=settings.embedding_model,
                    flag_client=flag_client,
                )
    return _embedding_service


_embedding_service: BgeM3EmbeddingService | None = None




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
        manifest = JsonFileManifestStore(os.path.join(_REPO_ROOT, "data", "ingest_manifest.json"))
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
        working_memory: 工作记忆。
        episodic: 情景记忆。
        scheduler: 注入调度器。
        semantic_cache: 语义缓存（L1 ANN + L2 Redis）。
    """

    def __init__(
        self,
        redis: RedisClient,
        qdrant: QdrantDBClient,
        working_memory: "WorkingMemory",
        episodic: "EpisodicMemory",
        scheduler: "MemoryScheduler",
        semantic_cache: "SemanticCache",
    ) -> None:
        self.redis = redis
        self.qdrant = qdrant
        self.working_memory = working_memory
        self.episodic = episodic
        self.scheduler = scheduler
        self.semantic_cache = semantic_cache


_memory_stack: MemoryStack | None = None
_memory_stack_lock = asyncio.Lock()


async def close_all_clients() -> None:
    """关闭所有单例客户端（lifespan 关闭期调用，P0-02/P0-03）。"""
    global _neo4j_client, _qdrant_client, _es_client, _redis_client, _memory_stack
    for client in (_neo4j_client, _qdrant_client, _es_client, _redis_client):
        if client is not None:
            try:
                await client.close()  # type: ignore[union-attr]
            except Exception:
                pass
    if _memory_stack is not None:
        for c in (_memory_stack.redis, _memory_stack.qdrant):
            try:
                await c.close()
            except Exception:
                pass
        _memory_stack = None
    _neo4j_client = _qdrant_client = _es_client = _redis_client = None

# 记忆层策略参数（config/reliability.yaml memory 节，读取失败用默认；
# 冷启动生效，J18 边界见 01 §7）— 用 os.path.abspath 避免 Path.resolve → os.getcwd 阻塞
_MEMORY_CFG_YAML = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
    "reliability.yaml",
)
# 启动期预缓存，避免首个 async 节点内读盘触发 Blocking
_MEMORY_CFG_CACHE: dict[str, Any] | None = None
try:
    with open(_MEMORY_CFG_YAML, encoding="utf-8") as _f:
        _raw_mem = yaml.safe_load(_f) or {}
        _MEMORY_CFG_CACHE = _raw_mem.get("memory") or None
except Exception:
    _MEMORY_CFG_CACHE = None


def _cast_memory_value(raw: Any, default: Any) -> Any:
    """类型安全转换：bool 特殊处理，避免 bool(\"false\")==True 陷阱（P0-02/M-01）。"""
    if raw is None:
        return default
    if isinstance(default, bool):
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        return bool(raw)
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(raw)
        except (ValueError, TypeError):
            return default
    if isinstance(default, float):
        try:
            return float(raw)
        except (ValueError, TypeError):
            return default
    return type(default)(raw)


def _load_memory_config() -> dict[str, Any]:
    """从 reliability.yaml 读取记忆层参数（启动期已缓存，async 内零 I/O）。

    Returns:
        {l1_hit_threshold, l1_ttl_seconds, l2_ttl_seconds,
         dedup_similarity_threshold, working_turns, wm_max_turns,
         wm_ttl_days, episodic_top_m, episodic_retention_days,
         summaries_cap}。
    """
    defaults: dict[str, Any] = {
        "l1_hit_threshold": 0.95,
        "l1_ttl_seconds": 3600,
        "l2_ttl_seconds": 600,
        "dedup_similarity_threshold": 0.92,
        "working_turns": 6,
        "wm_max_turns": 10,
        "wm_ttl_days": 7,
        "episodic_top_m": 3,
        "episodic_retention_days": 180,
        "summaries_cap": 20,
    }
    # 优先用启动期缓存，避免每次 async 内读盘
    if _MEMORY_CFG_CACHE is not None:
        return {key: _cast_memory_value(_MEMORY_CFG_CACHE.get(key, default), default) for key, default in defaults.items()}
    try:
        with open(_MEMORY_CFG_YAML, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        section = cfg.get("memory") or {}
        return {key: _cast_memory_value(section.get(key, default), default) for key, default in defaults.items()}
    except Exception:  # noqa: BLE001 - 配置缺失/损坏用默认
        return defaults


async def get_memory_stack() -> MemoryStack:
    """获取记忆层服务栈单例（客户端连接均首用时惰性建立）。

    Returns:
        MemoryStack: 组装完成的记忆层组件集合。
    """
    global _memory_stack
    if _memory_stack is None:
        async with _memory_stack_lock:
            if _memory_stack is None:
                settings = get_settings()
                mem = _load_memory_config()
                redis = RedisClient(
                    host=settings.redis_host, port=settings.redis_port, db=settings.redis_db
                )
                qdrant = QdrantDBClient(host=settings.qdrant_host, port=settings.qdrant_port)
                embedder = await get_embedding_service()
                working_memory = WorkingMemory(
                    redis,
                    max_turns=mem["wm_max_turns"],
                    ttl_seconds=mem["wm_ttl_days"] * 86400,
                )
                episodic = EpisodicMemory(
                    qdrant, embedder, retention_days=mem["episodic_retention_days"]
                )
                scheduler = MemoryScheduler(
                    working_memory,
                    episodic,
                    embedder,
                    working_turns=mem["working_turns"],
                    episodic_top_m=mem["episodic_top_m"],
                    dedup_similarity_threshold=mem["dedup_similarity_threshold"],
                )
                semantic_cache = SemanticCache(
                    qdrant=qdrant,
                    embedder=embedder,
                    redis=redis,
                    threshold=mem["l1_hit_threshold"],
                    l1_ttl_seconds=mem["l1_ttl_seconds"],
                    l2_ttl_seconds=mem["l2_ttl_seconds"],
                )
                _memory_stack = MemoryStack(
                    redis=redis,
                    qdrant=qdrant,
                    working_memory=working_memory,
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
