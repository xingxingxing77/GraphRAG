"""
分数计算与排序工具（架构 L5 · 单元 4.2）。

提供 Reranker 相关的分数计算、排序与证据选择辅助函数。
"""

# --- 本地模块 ---
from app.core.models import RetrievalResult


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


def select_evidence(
    reranked: list[tuple[RetrievalResult, float]],
    threshold: float,
    top_k: int,
) -> list[tuple[RetrievalResult, float]]:
    """证据选择编排（架构工作流：阈值过滤 → Top-K 截断，单元 4.2）。

    准出口径：送入 Agent 的证据数量 ≤ Top-K 且含分数。

    Args:
        reranked: 精排输出 (结果, 精排分) 列表（已降序）。
        threshold: 分数阈值（score ≥ threshold 保留，边界含）。
        top_k: 截断数量。

    Returns:
        过滤并截断后的 (结果, 分) 列表。
    """
    kept = [(d, s) for d, s in reranked if s >= threshold]
    return kept[:top_k]
