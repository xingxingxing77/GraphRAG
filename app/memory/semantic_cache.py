"""
语义缓存（单元 8.3，J22/H2，04 §3.3 + 04 §4）。

两级结构（命名以 04 为唯一权威）：
- L1：Qdrant `rag_cache` 集合 ANN top-1，score ≥ 0.95 视为命中——
  Redis 无原生向量检索能力，精确文本 hash 无法匹配同义改写，
  故 L1 必须走向量相似度（架构 H2 决策原文）；
- L2：Redis `l2:ret:{norm_hash}` 精确 hash 检索结果缓存，TTL 600s。

可靠性约定（07 A-11）：Qdrant/Embedding 异常一律返回降级 miss
（degraded=True），调用方置 X-Degraded: no-cache，缓存永不阻塞主链路。
single-flight：同键并发 miss 合并为一次回源加载（11 路线图 Phase 4）。
"""

# --- 标准库 ---
import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

# --- 第三方库 ---
from pydantic import BaseModel, Field
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct, Range

# --- 本地模块 ---
from app.core.models import Citation
from app.db.qdrant_client import QdrantDBClient
from app.db.redis_client import RedisClient
from app.embedding.base import EmbeddingService

logger = logging.getLogger(__name__)

# L1 命中阈值（H2：top-1 score ≥ 0.95）
L1_HIT_THRESHOLD = 0.95

# 集合与 Key（04 §3.3 / §4 唯一命名出处）
RAG_CACHE_COLLECTION = "rag_cache"
L2_KEY_PREFIX = "l2:ret:"

# 缓存条目 point ID 派生命名空间（同问题恒同 ID → 幂等覆盖写）
_POINT_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "graphrag://rag-cache-point")


class L1Lookup(BaseModel):
    """L1 查询结果（内部服务载荷，端点层映射为 PrecheckResponse）。

    Attributes:
        hit: 是否命中（score ≥ 0.95）。
        degraded: 存储异常导致的降级 miss（X-Degraded: no-cache 依据）。
        degraded_stage: 降级发生阶段（embedding | qdrant），仅 degraded=True 时有值。
        cache_score: 命中相似度分数。
        matched_query: 命中的缓存问题原文。
        answer: 缓存答案。
        citations: 缓存引用列表。
        model: 产出该答案的模型条目名。
    """

    hit: bool = False
    degraded: bool = False
    degraded_stage: str | None = None
    cache_score: float | None = None
    matched_query: str | None = None
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    model: str | None = None


class L1Entry(BaseModel):
    """待写入 L1 的答案条目（仅非个性化答案，H2）。"""

    question: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    matched_doc_ids: list[str] = Field(default_factory=list)
    latency_tier: str = "standard"
    model: str = ""


class SemanticCache:
    """语义缓存管理器（L1 Qdrant ANN + L2 Redis 精确 hash）。

    Attributes:
        qdrant: Qdrant 客户端。
        embedder: Embedding 服务（dense 通道）。
        redis: Redis 客户端（L2）。
        threshold: L1 命中阈值。
        l1_ttl_seconds: L1 应用层 TTL（每日 purge_expired 清理）。
        l2_ttl_seconds: L2 Redis TTL。
    """

    def __init__(
        self,
        qdrant: QdrantDBClient,
        embedder: EmbeddingService,
        redis: RedisClient,
        *,
        threshold: float = L1_HIT_THRESHOLD,
        l1_ttl_seconds: int = 3600,
        l2_ttl_seconds: int = 600,
        embedding_model: str = "",
    ) -> None:
        """初始化语义缓存。

        Args:
            qdrant: Qdrant 客户端。
            embedder: Embedding 服务（dense 通道）。
            redis: Redis 客户端（L2）。
            threshold: L1 命中阈值。
            l1_ttl_seconds: L1 应用层 TTL（每日 purge_expired 清理）。
            l2_ttl_seconds: L2 Redis TTL。
            embedding_model: 向量模型名（M6：进 point_id 材料与 payload
                过滤，换模型后新旧向量处于不同语义空间，必须互相隔离
                防缓存污染；空串仅用于测试替身）。
        """
        self.qdrant = qdrant
        self.embedder = embedder
        self.redis = redis
        self.threshold = threshold
        self.l1_ttl_seconds = l1_ttl_seconds
        self.l2_ttl_seconds = l2_ttl_seconds
        self.embedding_model = embedding_model
        # single-flight：norm_hash → 回源任务（并发同查询合并为一次加载）
        self._inflight: dict[str, asyncio.Task[L1Lookup]] = {}
        self._inflight_lock = asyncio.Lock()

    # ---------- 工具 ----------

    @staticmethod
    def normalize(text: str) -> str:
        """查询规范化：压缩空白并小写（norm_hash 口径，04 §4）。"""
        return " ".join(text.split()).lower()

    @classmethod
    def norm_hash(cls, query: str, params: dict[str, object] | None = None) -> str:
        """规范化哈希：sha256(规范化查询+参数) 前 24 位（04 §4）。"""
        material = cls.normalize(query)
        if params:
            material += "|" + json.dumps(params, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]

    async def _query_vector(self, query: str) -> list[float]:
        """查询文本 → dense 向量（BGE-M3 dense 通道，M7：dense-only）。"""
        vector = (await self.embedder.embed_dense([query]))[0]
        if not vector:
            raise ValueError("embedding 返回空 dense 向量")
        return vector

    # ---------- L1：Qdrant rag_cache ----------

    async def get_l1(self, query: str) -> L1Lookup:
        """ANN top-1 查询 L1 语义缓存（异常降级为 miss，A-11）。

        读侧同时过滤过期点（created_at ≥ now-TTL），避免日清间隙
        返回陈旧条目。异常细粒度记录阶段并上报指标，永不抛错。

        Args:
            query: 用户原始查询（改写前，04 §3.3 向量口径）。

        Returns:
            L1Lookup: 命中详情或（降级）miss（附 degraded_stage）。
        """
        try:
            try:
                vector = await self._query_vector(query)
            except Exception as exc:  # noqa: BLE001 - embedding 阶段
                logger.warning(
                    "L1 缓存降级 no-cache（embedding 阶段 query=%.30s）: %s: %s",
                    query,
                    type(exc).__name__,
                    exc,
                )
                try:
                    from app.api.metrics import record_degraded  # 延迟导入防循环

                    record_degraded("no-cache")
                except Exception:
                    pass
                return L1Lookup(hit=False, degraded=True, degraded_stage="embedding")
            fresh_from = int(time.time()) - self.l1_ttl_seconds
            flt = Filter(
                must=[
                    FieldCondition(key="created_at", range=Range(gte=float(fresh_from))),
                    # M6：只命中同一向量模型的条目——不同模型/维度的向量
                    # 不可比，跨模型命中会返回语义无关的旧答案
                    FieldCondition(
                        key="embedding_model",
                        match=MatchValue(value=self.embedding_model),
                    ),
                ]
            )
            try:
                hits = await self.qdrant.search(
                    RAG_CACHE_COLLECTION, vector, top_k=1, filter_condition=flt
                )
            except Exception as exc:  # noqa: BLE001 - qdrant 阶段
                logger.warning(
                    "L1 缓存降级 no-cache（qdrant 阶段 query=%.30s）: %s: %s",
                    query,
                    type(exc).__name__,
                    exc,
                )
                try:
                    from app.api.metrics import record_degraded

                    record_degraded("no-cache")
                except Exception:
                    pass
                return L1Lookup(hit=False, degraded=True, degraded_stage="qdrant")
        except Exception as exc:  # noqa: BLE001 - 兜底（不应到达）
            logger.warning(
                "L1 缓存降级 no-cache（未知阶段 query=%.30s）: %s: %s",
                query,
                type(exc).__name__,
                exc,
            )
            return L1Lookup(hit=False, degraded=True, degraded_stage="unknown")
        if not hits:
            return L1Lookup(hit=False)
        top = hits[0]
        if top["score"] < self.threshold:
            return L1Lookup(hit=False, cache_score=top["score"])
        payload = top["payload"]
        try:
            citations = [
                Citation.model_validate(item)
                for item in json.loads(payload.get("citations_json", "[]"))
            ]
        except (json.JSONDecodeError, ValueError):
            citations = []
        return L1Lookup(
            hit=True,
            cache_score=top["score"],
            matched_query=str(payload.get("question", "")),
            answer=str(payload.get("answer", "")),
            citations=citations,
            model=payload.get("model"),
        )

    async def set_l1(self, entry: L1Entry) -> None:
        """写入 L1 缓存条目（幂等：同问题 uuid5 覆盖写）。

        仅允许非个性化答案进入（个性化上下文注入过的回答由调用方
        负责不落缓存，H2）。写入前幂等确保集合存在（含 payload 索引自愈）；
        失败静默——缓存写失败不影响主链路。

        Args:
            entry: 待缓存条目。
        """
        try:
            await self.qdrant.ensure_collection(RAG_CACHE_COLLECTION)
            # 自愈：确保 created_at 范围索引存在（缺失会导致过期过滤不生效，变相恒 miss）
            try:
                await self.qdrant.ensure_payload_index(
                    RAG_CACHE_COLLECTION, "created_at"
                )
                await self.qdrant.ensure_payload_index(
                    RAG_CACHE_COLLECTION, "embedding_model"
                )
            except Exception as exc:
                logger.debug("ensure_payload_index 自愈忽略: %s", exc)
            vector = await self._query_vector(entry.question)
            # M6：point_id 材料含向量模型——同问题换模型后写为新点，
            # 旧模型点由读侧 Filter 天然隔离
            point_id = str(
                uuid.uuid5(
                    _POINT_ID_NAMESPACE,
                    f"{self.embedding_model}|{self.normalize(entry.question)}",
                )
            )
            point = PointStruct(
                id=point_id,
                vector={"dense": vector},
                payload={
                    "question": entry.question,
                    "answer": entry.answer,
                    "citations_json": json.dumps(
                        [c.model_dump() for c in entry.citations],
                        ensure_ascii=False,
                    ),
                    "matched_doc_ids": entry.matched_doc_ids,
                    "latency_tier": entry.latency_tier,
                    "created_at": int(time.time()),
                    "model": entry.model,
                    "embedding_model": self.embedding_model,
                },
            )
            await self.qdrant.upsert_points(RAG_CACHE_COLLECTION, [point])
        except Exception as exc:  # noqa: BLE001 - 写失败不影响主链路
            logger.warning("set_l1 写入失败（question=%.30s）: %s: %s", entry.question, type(exc).__name__, exc)
            return

    async def invalidate_doc(self, doc_id: str) -> int:
        """按文档 ID 反查失效受影响的 L1 条目（04 §7 失效联动）。

        Args:
            doc_id: 新增/删除的文档 ID。

        Returns:
            删除的缓存条目数（admin cache/clear purged 计数来源）。
        """
        try:
            return await self.qdrant.delete_by_payload_match(
                RAG_CACHE_COLLECTION, "matched_doc_ids", doc_id
            )
        except Exception as exc:  # noqa: BLE001 - 失效联动失败不阻塞主流程
            logger.warning("invalidate_doc 失效联动失败（doc_id=%s）: %s", doc_id, exc)
            return 0

    async def purge_expired(self, now: int | None = None) -> int:
        """清理过期 L1 点（应用层定时任务，Qdrant 无原生 TTL）。

        Args:
            now: 当前 unix 秒（默认取系统时间）。

        Returns:
            删除的点数（异常时返回 0）。
        """
        current = now if now is not None else int(time.time())
        try:
            return await self.qdrant.delete_created_before(
                RAG_CACHE_COLLECTION, "created_at", current - self.l1_ttl_seconds
            )
        except Exception as exc:  # noqa: BLE001 - 定时任务失败仅记录不抛出
            logger.warning("purge_expired 失败: %s: %s", type(exc).__name__, exc)
            return 0

    # ---------- single-flight ----------

    async def get_or_load(self, query: str, loader: Callable[[], Awaitable[L1Entry]]) -> L1Lookup:
        """带 single-flight 的查取：命中直接返回；未命中合并并发回源并回填。

        同一规范化查询的并发调用共享同一个回源任务，避免缓存击穿
        （11 路线图 Phase 4）。回源结果经 set_l1 幂等回填。

        Args:
            query: 用户查询。
            loader: 未命中时的回源协程工厂（返回可缓存条目）。

        Returns:
            L1Lookup: 命中、回源成功（含新条目内容）或降级 miss。
        """
        first = await self.get_l1(query)
        if first.hit or first.degraded:
            return first
        key = self.norm_hash(query)
        async with self._inflight_lock:
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(self._load_and_store(query, loader))
                self._inflight[key] = task
        try:
            return await task
        finally:
            async with self._inflight_lock:
                if self._inflight.get(key) is task:
                    del self._inflight[key]

    async def _load_and_store(
        self, query: str, loader: Callable[[], Awaitable[L1Entry]]
    ) -> L1Lookup:
        """执行回源加载并回填 L1（single-flight 共享体）。"""
        try:
            entry = await loader()
        except Exception:  # noqa: BLE001 - 回源失败按普通 miss 返回
            return L1Lookup(hit=False)
        await self.set_l1(entry)
        return L1Lookup(
            hit=True,
            cache_score=1.0,
            matched_query=entry.question,
            answer=entry.answer,
            citations=entry.citations,
            model=entry.model,
        )

    # ---------- L2：Redis l2:ret:{norm_hash} ----------

    async def get_l2(
        self, query: str, params: dict[str, object] | None = None
    ) -> list[dict[str, object]] | None:
        """读取 L2 检索结果缓存（异常返回 None，不阻塞）。"""
        try:
            raw = await self.redis.get(L2_KEY_PREFIX + self.norm_hash(query, params))
        except Exception as exc:  # noqa: BLE001
            logger.debug("get_l2 Redis 异常（query=%.30s）: %s: %s", query, type(exc).__name__, exc)
            return None
        if raw is None:
            return None
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, list) else None

    async def set_l2(
        self,
        query: str,
        results: list[dict[str, object]],
        params: dict[str, object] | None = None,
    ) -> None:
        """写入 L2 检索结果缓存（TTL 600s，写失败静默）。"""
        try:
            await self.redis.set(
                L2_KEY_PREFIX + self.norm_hash(query, params),
                json.dumps(results, ensure_ascii=False),
                ttl=self.l2_ttl_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("set_l2 Redis 异常（query=%.30s）: %s: %s", query, type(exc).__name__, exc)
            return
