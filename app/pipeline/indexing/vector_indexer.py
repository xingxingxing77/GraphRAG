"""
Qdrant 向量索引器。

将增强后的文档块向量化并存入 Qdrant Collection，
支持密集向量和稀疏向量的批量写入。
"""

# --- 标准库 ---
import logging
from typing import Any, Protocol

# --- 本地模块 ---
from app.pipeline.base import EnrichedChunk
from app.db.qdrant_client import QdrantDBClient

logger = logging.getLogger(__name__)


class EmbeddingServiceLike(Protocol):
    """嵌入服务的协议接口（用于类型提示）。"""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """将文本列表嵌入为向量列表。"""
        ...

    async def embed_sparse(self, texts: list[str]) -> list[dict[int, float]]:
        """将文本列表嵌入为稀疏向量列表。"""
        ...


class VectorIndexer:
    """Qdrant 向量索引器。

    将 EnrichedChunk 列表向量化后批量写入 Qdrant，
    支持密集向量和稀疏向量双通道。

    Attributes:
        db_client: QdrantDBClient 实例。
        collection_name: 目标 Collection 名称。
        batch_size: 批量写入大小。
    """

    def __init__(
        self,
        db_client: QdrantDBClient,
        collection_name: str = "documents",
        batch_size: int = 100,
    ) -> None:
        """初始化 VectorIndexer。

        Args:
            db_client: QdrantDBClient 实例。
            collection_name: 目标 Collection 名称，默认 "documents"。
            batch_size: 批量写入大小，默认 100。
        """
        self.db_client = db_client
        self.collection_name = collection_name
        self.batch_size = batch_size

    async def index(
        self,
        chunks: list[EnrichedChunk],
        embedding_service: EmbeddingServiceLike,
    ) -> None:
        """将文档块向量化并存入 Qdrant。

        处理流程：
        1. 提取所有 chunk 的文本内容。
        2. 调用 embedding_service 生成密集向量和稀疏向量。
        3. 构建 Qdrant PointStruct 列表。
        4. 按 batch_size 分批调用 db_client.upsert_points。

        Args:
            chunks: 待索引的增强文档块列表。
            embedding_service: 嵌入服务实例。

        Raises:
            ConnectionError: 无法连接 Qdrant。
        """
        # TODO: 1. 提取文本列表
        # TODO: 2. 批量生成密集向量
        # TODO: 3. 批量生成稀疏向量（如支持）
        # TODO: 4. 构建 PointStruct（id=hash, vector, payload=metadata）
        # TODO: 5. 分批 upsert
        # TODO: 6. 记录索引日志
        raise NotImplementedError
