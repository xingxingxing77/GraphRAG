"""
Elasticsearch 全文检索器（架构 L3 · J5/J6 协同 · 单元 3.4）。

ES↔Neo4j 协同检索流程（J6 定案）：
1. ES IK match 召回 Top-M 实体/文档片段（毫秒级）；
2. 提取命中 entity_id / canonical_name 回投 Neo4j 一跳邻域扩展；
3. 合并为 source="fulltext" 的 RetrievalResult。

一致性：ES 允许秒级滞后，最终以 Neo4j 为准；ES 命中但 Neo4j 已删
的窗口内回查为空则 null-skip（容忍秒级窗口）。
实现 BaseRetriever 协议：独立超时 + 失败降级空列表（D5）。
"""

# --- 标准库 ---
import asyncio
import logging
from typing import Any

# --- 本地模块 ---
from app.core.models import RetrievalResult, SourceKind
from app.db.es_client import ENTITIES_ALIAS, CHUNKS_ALIAS, ESClient
from app.db.neo4j_client import Neo4jClient
from app.retrieval.base import BaseRetriever
from app.retrieval.dense_retriever import stable_hash

logger = logging.getLogger(__name__)

# 独立超时（reliability.yaml timeouts_seconds.elasticsearch）
_ES_TIMEOUT_S = 3.0

# Neo4j 一跳邻域扩展模板（04 §5.4 Local Search）
_ONE_HOP_CYPHER = (
    "MATCH (e:Entity {canonical_name: $entity}) "
    "OPTIONAL MATCH (e)-[r]-(n) "
    "RETURN e.canonical_name AS root, "
    "       collect(DISTINCT {rel: type(r), node: n.canonical_name}) AS neighbors"
)


class FullTextRetriever(BaseRetriever):
    """ES 全文检索器（J6 协同）。

    Attributes:
        name: 检索来源（SourceKind.FULLTEXT）。
        error_count: 失败计数器。
    """

    name: SourceKind = SourceKind.FULLTEXT

    def __init__(
        self,
        es_client: ESClient,
        neo4j_client: Neo4jClient,
        timeout_s: float = _ES_TIMEOUT_S,
    ) -> None:
        """初始化 ES 全文检索器。

        Args:
            es_client: ES 客户端。
            neo4j_client: Neo4j 客户端（回投扩展用）。
            timeout_s: 独立超时（秒）。
        """
        self.es_client = es_client
        self.neo4j_client = neo4j_client
        self.timeout_s = timeout_s
        self.error_count = 0

    async def retrieve(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        """执行 ES 全文检索 + Neo4j 回投扩展（超时/失败降级空列表）。

        Args:
            query: 查询文本。
            top_k: ES 召回 Top-M 数量。
            filters: 预留过滤条件。

        Returns:
            检索结果列表（source="fulltext"），失败返回空列表。
        """
        try:
            return await asyncio.wait_for(
                self._retrieve(query, top_k), timeout=self.timeout_s
            )
        except Exception as exc:  # noqa: BLE001 - 含超时，降级空列表
            self.error_count += 1
            logger.warning("fulltext 检索失败（降级空列表）: %s", exc)
            return []

    async def _retrieve(self, query: str, top_k: int) -> list[RetrievalResult]:
        """实际协同逻辑（ES 召回 → Neo4j 回投 → 合并）。

        Args:
            query: 查询文本。
            top_k: ES 召回数量。

        Returns:
            检索结果列表。
        """
        # 1. ES IK match 召回（rag_entities.name 优先，回退 rag_chunks.content）
        hits = await self._es_recall(query, top_k)

        # 2. 回投 Neo4j 一跳扩展（容忍秒级窗口，null-skip）
        results: list[RetrievalResult] = []
        for hit in hits:
            src = dict(hit.get("source") or {})
            canonical = src.get("canonical_name") or src.get("name") or ""
            content = src.get("description") or src.get("content") or canonical
            if canonical:
                expansion = await self._neo4j_expand(str(canonical))
                if expansion:
                    content = expansion
            results.append(
                RetrievalResult(
                    result_id=f"{self.name.value}:{stable_hash(str(hit.get('id')), str(canonical))}",
                    chunk_id=src.get("chunk_id"),
                    content=str(content),
                    score=float(hit.get("score") or 0.0),
                    source=self.name,
                    doc_id=src.get("doc_id"),
                    metadata={"entity_id": hit.get("id"), "canonical_name": str(canonical)},
                )
            )
        # M2：BM25 无界（通常 ≥1）→ 按本批最大分归一到 [0,1]，
        # 否则一条 BM25 结果即可让 A2「证据充分」短路恒真
        max_score = max((r.score for r in results), default=0.0)
        if max_score > 0:
            results = [r.model_copy(update={"score": r.score / max_score}) for r in results]
        results.sort(key=lambda x: -x.score)
        return results[:top_k]

    async def _es_recall(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """ES IK match 召回（rag_entities 优先，回退 rag_chunks）。

        Args:
            query: 查询文本。
            top_k: 召回数量。

        Returns:
            命中列表（含 id/score/source 字段）。
        """
        try:
            hits = await self.es_client.search(ENTITIES_ALIAS, "name", query, top_k)
            if hits:
                return hits
        except Exception:  # noqa: BLE001 - 回退 rag_chunks
            pass
        try:
            return await self.es_client.search(CHUNKS_ALIAS, "content", query, top_k)
        except Exception:  # noqa: BLE001 - ES 无索引/不可达
            return []

    async def _neo4j_expand(self, canonical: str) -> str:
        """Neo4j 一跳邻域扩展（容忍秒级窗口，空则返回空串）。

        Args:
            canonical: 规范实体名。

        Returns:
            序列化子图文本；Neo4j 无该实体（已删/未同步）返回空串。
        """
        try:
            rows = await self.neo4j_client.execute_cypher(
                _ONE_HOP_CYPHER, {"entity": canonical}
            )
        except Exception:  # noqa: BLE001 - Neo4j 不可达则 null-skip
            return ""
        if not rows or not rows[0].get("root"):
            return ""
        row = rows[0]
        neighbors = [n for n in (row.get("neighbors") or []) if n.get("node")]
        if not neighbors:
            return ""
        desc = "; ".join(f"{canonical}-[{n.get('rel')}]->{n.get('node')}" for n in neighbors)
        return f"实体「{canonical}」关联：{desc}"
