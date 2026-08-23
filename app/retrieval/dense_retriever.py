"""
Qdrant 密集向量检索器。

使用 BGE-M3 密集向量进行语义相似度检索。
"""

# --- 标准库 ---
from typing import Any

# --- 本地模块 ---
from app.core.models import RetrievalResult
from app.db.qdrant_client import QdrantDBClient
from app.embedding.base import EmbeddingService


class DenseRetriever:
    """密集向量检索器。

    通过 BGE-M3 密集向量在 Qdrant 中执行语义相似度检索。
    """

    def __init__(
        self,
        qdrant_client: QdrantDBClient,
        embedding_service: EmbeddingService,
        collection_name: str,
    ) -> None:
        """初始化密集向量检索器。

        Args:
            qdrant_client: Qdrant 客户端。
            embedding_service: Embedding 服务。
            collection_name: Qdrant Collection 名称。
        """
        self.qdrant_client = qdrant_client
        self.embedding_service = embedding_service
        self.collection_name = collection_name

    async def search(
        self,
        query: str,
        top_k: int = 10,
        filter_condition: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        """执行密集向量语义检索。

        Args:
            query: 查询文本。
            top_k: 返回数量。
            filter_condition: 元数据过滤条件。

        Returns:
            检索结果列表，按分数降序排列。
        """
        # TODO: 调用 embedding_service 获取 dense 向量
        # TODO: 调用 qdrant_client.search 执行检索
        # TODO: 格式化结果为 RetrievalResult 列表
        raise NotImplementedError
