"""
检索结果分数归一化器。

将不同检索器的分数统一到 [0, 1] 区间。
"""

# --- 本地模块 ---
from app.retrieval.dense_retriever import RetrievalResult


class ScoreNormalizer:
    """分数归一化器。

    不同检索器返回的分数范围不同（如 cosine: [0,1]、dot product: 无界），
    需要统一到同一区间以便融合。
    """

    @staticmethod
    def min_max_normalize(results: list[RetrievalResult]) -> list[RetrievalResult]:
        """Min-Max 归一化到 [0, 1]。

        Args:
            results: 检索结果列表。

        Returns:
            分数已归一化的结果列表。
        """
        # TODO: 找出 min/max 分数，线性映射到 [0,1]
        raise NotImplementedError

    @staticmethod
    def rank_normalize(results: list[RetrievalResult]) -> list[RetrievalResult]:
        """基于排名的归一化。

        分数最高的文档得 1.0，最低的得 0.0，按排名线性递减。

        Args:
            results: 检索结果列表（需已排序）。

        Returns:
            分数已归一化的结果列表。
        """
        # TODO: 按排名计算归一化分数
        raise NotImplementedError
