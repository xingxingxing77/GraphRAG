"""
Qdrant 向量索引器（架构 P6 · 04 §3.1 · 单元 3.1）。

将 EnrichedChunk 向量化后按 doc_type 路由写入 rag_{doc_type} 集合：
- dense + sparse 双通道批量 upsert（batch_size=100）；
- point id 由 chunk_id 确定性派生，幂等重放 count 不变；
- payload 键严格按 04 §3.1：doc_id/chunk_id/source/doc_type 必填，
  附加 content/keywords/title_path/quality_score/access_count。
"""

# --- 标准库 ---
import logging
from typing import Any

# --- 第三方库 ---
from qdrant_client.models import PointStruct, SparseVector

# --- 本地模块 ---
from app.core.models import EnrichedChunk, MetadataKeys
from app.db.qdrant_client import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    QdrantDBClient,
    point_id_from_chunk_id,
)
from app.embedding.base import EmbeddingService

logger = logging.getLogger(__name__)

# 业务集合命名前缀（04 §3.1：rag_{doc_type}）
_COLLECTION_PREFIX = "rag_"


def collection_for(doc_type: str) -> str:
    """按 doc_type 计算业务集合名称。

    Args:
        doc_type: 文档类型（recipes/tips/knowledge...）。

    Returns:
        Collection 名称（rag_{doc_type}）。
    """
    return f"{_COLLECTION_PREFIX}{doc_type}"


def build_payload(chunk: EnrichedChunk, source: str, doc_type: str) -> dict[str, Any]:
    """构建 04 §3.1 规范的 payload。

    Args:
        chunk: 增强文档块。
        source: 来源标识（必填键 source）。
        doc_type: 文档类型（必填键 doc_type）。

    Returns:
        payload 字典。
    """
    meta = chunk.chunk.metadata
    return {
        MetadataKeys.DOC_ID: chunk.chunk.doc_id,
        MetadataKeys.CHUNK_ID: chunk.chunk.chunk_id,
        MetadataKeys.SOURCE: source,
        MetadataKeys.DOC_TYPE: doc_type,
        MetadataKeys.TITLE_PATH: list(chunk.chunk.title_path),
        MetadataKeys.QUALITY_SCORE: float(
            meta.get(MetadataKeys.QUALITY_SCORE, 0.0) or 0.0
        ),
        "content": chunk.chunk.content,
        "keywords": list(chunk.keywords),
        "access_count": 0,
    }


class VectorIndexer:
    """Qdrant 向量索引器（P6）。

    Attributes:
        db_client: QdrantDBClient 实例。
        embedding_service: 统一 Embedding 服务（dense+sparse 双通道）。
        batch_size: 批量写入大小。
    """

    def __init__(
        self,
        db_client: QdrantDBClient,
        embedding_service: EmbeddingService,
        batch_size: int = 100,
    ) -> None:
        """初始化 VectorIndexer。

        Args:
            db_client: QdrantDBClient 实例。
            embedding_service: 统一 Embedding 服务。
            batch_size: 批量写入大小（架构 P6 = 100）。
        """
        self.db_client = db_client
        self.embedding_service = embedding_service
        self.batch_size = batch_size

    async def index(
        self,
        chunks: list[EnrichedChunk],
        source: str,
        doc_type: str,
    ) -> int:
        """将文档块向量化并按 doc_type 路由写入 Qdrant。

        Args:
            chunks: 待索引的增强文档块列表。
            source: 来源标识（payload source 键）。
            doc_type: 文档类型（决定 rag_{doc_type} 集合）。

        Returns:
            写入的点数量。
        """
        if not chunks:
            return 0
        collection = collection_for(doc_type)
        await self.db_client.ensure_collection(collection)

        texts = [c.chunk.content for c in chunks]
        result = await self.embedding_service.embed(texts)

        points: list[PointStruct] = []
        for i, chunk in enumerate(chunks):
            dense = result.dense[i] if i < len(result.dense) else []
            sparse_dict = result.sparse[i] if i < len(result.sparse) else {}
            indices = sorted(sparse_dict.keys())
            vectors: dict[str, Any] = {DENSE_VECTOR_NAME: dense}
            if indices:
                vectors[SPARSE_VECTOR_NAME] = SparseVector(
                    indices=indices,
                    values=[sparse_dict[k] for k in indices],
                )
            points.append(
                PointStruct(
                    id=point_id_from_chunk_id(chunk.chunk.chunk_id),
                    vector=vectors,
                    payload=build_payload(chunk, source, doc_type),
                )
            )

        await self.db_client.upsert_points(
            collection, points, batch_size=self.batch_size
        )
        logger.info(
            "向量写入完成：collection=%s points=%d", collection, len(points)
        )
        return len(points)
