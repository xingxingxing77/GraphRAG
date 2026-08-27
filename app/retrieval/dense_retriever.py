"""
Qdrant 密集向量检索器（架构 L3 · 05 §3.2/§3.3 · 单元 3.3）。

使用 BGE-M3 密集向量在 Qdrant 业务集合执行语义相似度检索。
实现 BaseRetriever 协议（架构 §3.5）：
- result_id = f"dense:{stable_hash}"，全局唯一、融合层去重键；
- 独立超时（reliability.yaml timeouts_seconds.qdrant），超时/失败
  返回空列表 + 错误计数，不抛错（D5 降级）；
- score = Cosine 相似度原始分（归一化前，融合层负责归一化）。
"""

# --- 标准库 ---
import asyncio
import hashlib
import logging
from typing import Any

# --- 本地模块 ---
from app.core.models import RetrievalResult, SourceKind
from app.db.qdrant_client import QdrantDBClient
from app.embedding.base import EmbeddingService
from app.retrieval.base import BaseRetriever

logger = logging.getLogger(__name__)

# 独立超时（reliability.yaml timeouts_seconds.qdrant）
_QDRANT_TIMEOUT_S = 3.0


def stable_hash(*parts: str) -> str:
    """对若干片段计算稳定短哈希（result_id 用）。

    Args:
        *parts: 参与哈希的字符串片段。

    Returns:
        sha256 前 16 位十六进制。
    """
    h = hashlib.sha256("|".join(parts).encode("utf-8"))
    return h.hexdigest()[:16]


class DenseRetriever(BaseRetriever):
    """密集向量检索器。

    Attributes:
        name: 检索来源（SourceKind.DENSE）。
        error_count: 失败计数器（可观测 rag_retrieval_errors_total）。
    """

    name: SourceKind = SourceKind.DENSE

    def __init__(
        self,
        qdrant_client: QdrantDBClient,
        embedding_service: EmbeddingService,
        collection_names: list[str],
        timeout_s: float = _QDRANT_TIMEOUT_S,
    ) -> None:
        """初始化密集向量检索器。

        Args:
            qdrant_client: Qdrant 客户端。
            embedding_service: Embedding 服务（dense 通道）。
            collection_names: 业务集合列表（rag_{doc_type}）。
            timeout_s: 独立超时（秒）。
        """
        self.qdrant_client = qdrant_client
        self.embedding_service = embedding_service
        self.collection_names = collection_names
        self.timeout_s = timeout_s
        self.error_count = 0

    async def retrieve(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        """执行密集向量语义检索（超时/失败降级空列表）。

        Args:
            query: 查询文本。
            top_k: 每集合返回数量。
            filters: 预留过滤条件（暂未启用）。

        Returns:
            检索结果列表（Cosine 原始分降序），失败返回空列表。
        """
        try:
            return await asyncio.wait_for(
                self._retrieve(query, top_k, filters), timeout=self.timeout_s
            )
        except Exception as exc:  # noqa: BLE001 - 含超时，降级空列表
            self.error_count += 1
            logger.warning("dense 检索失败（降级空列表）: %s", exc)
            return []

    async def _retrieve(
        self, query: str, top_k: int, filters: dict[str, Any] | None
    ) -> list[RetrievalResult]:
        """实际检索逻辑（跨业务集合聚合）。

        Args:
            query: 查询文本。
            top_k: 每集合返回数量。
            filters: 预留过滤条件。

        Returns:
            聚合后的检索结果列表。
        """
        result = await self.embedding_service.embed([query])
        if not result.dense or not result.dense[0]:
            logger.warning("dense 嵌入返回空向量，降级空列表")
            return []
        query_vec = result.dense[0]

        hits: list[RetrievalResult] = []
        for collection in self.collection_names:
            raw = await self.qdrant_client.search(
                collection, query_vec, top_k=top_k
            )
            for r in raw:
                chunk_id = r.get("chunk_id") or ""
                hits.append(
                    RetrievalResult(
                        result_id=f"{self.name.value}:{stable_hash(chunk_id, r['id'])}",
                        chunk_id=chunk_id or None,
                        content=str(r.get("payload", {}).get("content", "")),
                        score=float(r["score"]),
                        source=self.name,
                        doc_id=str(r.get("payload", {}).get("doc_id") or "") or None,
                        metadata=dict(r.get("payload") or {}),
                    )
                )
        hits.sort(key=lambda x: -x.score)
        return hits[: top_k * len(self.collection_names)]
