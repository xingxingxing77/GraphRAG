"""
检索结果分数归一化器（架构 L4 · 单元 3.5）。

将不同检索器的分数统一到 [0, 1] 区间：cosine ∈ [0,1]、
Dot Product 无界、ES/启发分各异——归一化是加权融合的前置。
"""

# --- 本地模块 ---
from app.core.models import RetrievalResult


class ScoreNormalizer:
    """分数归一化器。

    所有方法返回新对象（model_copy），不修改入参。
    """

    @staticmethod
    def min_max_normalize(results: list[RetrievalResult]) -> list[RetrievalResult]:
        """Min-Max 归一化到 [0, 1]。

        单路退化处理：全部分数相同（含单条）时统一置 1.0。

        Args:
            results: 检索结果列表。

        Returns:
            分数已归一化的结果列表（顺序不变）。
        """
        if not results:
            return []
        scores = [r.score for r in results]
        lo, hi = min(scores), max(scores)
        span = hi - lo
        if span <= 1e-12:
            # 单路退化：所有分数相同 → 统一 1.0
            return [r.model_copy(update={"score": 1.0}) for r in results]
        return [
            r.model_copy(update={"score": (r.score - lo) / span}) for r in results
        ]

    @staticmethod
    def rank_normalize(results: list[RetrievalResult]) -> list[RetrievalResult]:
        """基于排名的归一化。

        分数最高得 1.0，最低得 0.0，按排名线性递减；
        单条退化为 1.0。

        Args:
            results: 检索结果列表（需已按分数降序排序）。

        Returns:
            分数已归一化的结果列表。
        """
        n = len(results)
        if n == 0:
            return []
        if n == 1:
            return [results[0].model_copy(update={"score": 1.0})]
        return [
            r.model_copy(update={"score": (n - 1 - i) / (n - 1)})
            for i, r in enumerate(results)
        ]
