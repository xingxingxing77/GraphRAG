"""
检索结果去重器。

基于文档 ID 或内容哈希进行去重和合并。
"""

# --- 标准库 ---
import hashlib

# --- 本地模块 ---
from app.retrieval.dense_retriever import RetrievalResult


class Deduplicator:
    """检索结果去重器。

    当同一条文档被多路检索器召回时，去除重复项，
    保留分数最高的一条记录。
    """

    @staticmethod
    def deduplicate(
        results: list[RetrievalResult],
        strategy: str = "content_hash",
    ) -> list[RetrievalResult]:
        """对检索结果去重。

        Args:
            results: 待去重的结果列表。
            strategy: 去重策略，``content_hash`` 基于内容哈希，
                ``metadata_id`` 基于元数据中的文档 ID。

        Returns:
            去重后的结果列表，保持原有排序。
        """
        # TODO: 根据策略计算去重 key
        # TODO: 保留同一 key 中分数最高的记录
        # TODO: 保持原有排序顺序
        raise NotImplementedError

    @staticmethod
    def _content_hash(content: str) -> str:
        """计算内容的 SHA-256 哈希。

        Args:
            content: 文档内容。

        Returns:
            SHA-256 哈希值。
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def merge_same_document(
        results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        """合并同一文档的多个 chunk。

        当同一父文档的多个子块被检索到时，合并为一条记录。

        Args:
            results: 检索结果列表。

        Returns:
            合并后的结果列表。
        """
        # TODO: 按 parent_id 分组
        # TODO: 合并同一文档的多个 chunk 内容
        raise NotImplementedError
