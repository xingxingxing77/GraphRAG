"""
分数计算与排序工具。

提供 Reranker 相关的分数计算和排序辅助函数。
"""

# --- 本地模块 ---
from app.retrieval.dense_retriever import RetrievalResult


def sort_by_score(results: list[RetrievalResult], descending: bool = True) -> list[RetrievalResult]:
    """按分数排序。

    Args:
        results: 检索结果列表。
        descending: 是否降序排列。

    Returns:
        排序后的结果列表。
    """
    return sorted(results, key=lambda r: r.score, reverse=descending)


def truncate_top_k(results: list[RetrievalResult], top_k: int) -> list[RetrievalResult]:
    """截断到 Top-K。

    Args:
        results: 检索结果列表。
        top_k: 保留数量。

    Returns:
        截断后的结果列表。
    """
    return results[:top_k]


def filter_by_threshold(
    results: list[RetrievalResult],
    threshold: float,
) -> list[RetrievalResult]:
    """过滤低于阈值的结果。

    Args:
        results: 检索结果列表。
        threshold: 最低分数阈值。

    Returns:
        过滤后的结果列表。
    """
    return [r for r in results if r.score >= threshold]
