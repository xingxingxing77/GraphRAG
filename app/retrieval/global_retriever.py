"""
社区摘要检索器（架构 L3 Global Search · P7-G5 · 单元 3.4）。

回答总结全局型问题（如"知识库覆盖哪些主题"）的唯一可行路径：
召回 (:Community) 社区摘要。实现 BaseRetriever 协议：
- result_id = f"global:{stable_hash}"；
- 独立超时 + 失败降级空列表（D5）；
- score = 关键词命中启发分（字符重合度 ∈ [0,1]，M2 归一口径）。
"""

# --- 标准库 ---
import asyncio
import logging
from typing import Any

# --- 本地模块 ---
from app.core.models import RetrievalResult, SourceKind
from app.db.neo4j_client import Neo4jClient
from app.retrieval.base import BaseRetriever
from app.retrieval.dense_retriever import stable_hash

logger = logging.getLogger(__name__)

# 独立超时（reliability.yaml timeouts_seconds.neo4j）
_NEO4J_TIMEOUT_S = 3.0

# Global Search：召回社区摘要（按 level 分层）
_GLOBAL_SEARCH_CYPHER = (
    "MATCH (m:Community) "
    "RETURN m.community_id AS community_id, m.level AS level, "
    "       m.summary AS summary "
    "ORDER BY m.level DESC "
    "LIMIT $limit"
)


class GlobalRetriever(BaseRetriever):
    """社区摘要检索器（Global Search）。

    Attributes:
        name: 检索来源（SourceKind.GLOBAL）。
        error_count: 失败计数器。
    """

    name: SourceKind = SourceKind.GLOBAL

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        timeout_s: float = _NEO4J_TIMEOUT_S,
    ) -> None:
        """初始化社区摘要检索器。

        Args:
            neo4j_client: Neo4j 客户端。
            timeout_s: 独立超时（秒）。
        """
        self.neo4j_client = neo4j_client
        self.timeout_s = timeout_s
        self.error_count = 0

    async def retrieve(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        """执行社区摘要检索（超时/失败降级空列表）。

        Args:
            query: 查询文本。
            top_k: 返回数量。
            filters: 预留过滤条件。

        Returns:
            检索结果列表（社区摘要文本），失败返回空列表。
        """
        try:
            return await asyncio.wait_for(
                self._retrieve(query, top_k), timeout=self.timeout_s
            )
        except Exception as exc:  # noqa: BLE001 - 含超时，降级空列表
            self.error_count += 1
            logger.warning("global 检索失败（降级空列表）: %s", exc)
            return []

    async def _retrieve(self, query: str, top_k: int) -> list[RetrievalResult]:
        """实际召回逻辑（社区摘要 + 关键词命中启发分）。

        Args:
            query: 查询文本。
            top_k: 返回数量。

        Returns:
            检索结果列表。
        """
        rows = await self.neo4j_client.execute_cypher(
            _GLOBAL_SEARCH_CYPHER, {"limit": top_k}
        )
        hits: list[RetrievalResult] = []
        query_tokens = set(query)
        for row in rows:
            summary = str(row.get("summary") or "")
            if not summary:
                continue
            # 关键词命中启发分（字符重合度；M2：去掉 1.0 基座，恒 ≥1 的
            # 原始口径会让 A2 短路/B3 修剪等 0-1 阈值消费失真）
            overlap = len(query_tokens & set(summary))
            score = overlap / max(1, len(query_tokens))
            community_id = str(row.get("community_id") or "")
            hits.append(
                RetrievalResult(
                    result_id=f"{self.name.value}:{stable_hash(community_id)}",
                    chunk_id=None,
                    content=summary,
                    score=score,
                    source=self.name,
                    doc_id=None,
                    metadata={
                        "community_id": community_id,
                        "level": int(row.get("level") or 0),
                        "source": "global",
                    },
                )
            )
        hits.sort(key=lambda x: -x.score)
        return hits[:top_k]
