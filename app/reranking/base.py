"""
Reranker 统一接口协议（架构 §3.5）。

实现约束（05 §3.3 async 三铁律 + 架构 H1）：
- FlagEmbedding 进程内同步推理必须 run_in_executor 包裹
- 经全局 semaphore 串行化（bulkhead，上限 1~2）
- 独立超时（reliability.yaml rerank_timeout），>2s 走 no-rerank
  降级返回原序粗排分数（D5，X-Degraded: no-rerank）
"""

# --- 标准库 ---
from typing import Protocol, runtime_checkable

# --- 本地模块 ---
from app.core.models import RetrievalResult


@runtime_checkable
class RerankerService(Protocol):
    """精排服务协议（第 5 层，Cross-Encoder 查询-文档对打分）。"""

    async def rerank(
        self,
        query: str,
        docs: list[RetrievalResult],
        top_k: int,
    ) -> list[tuple[RetrievalResult, float]]:
        """对候选证据精排。

        Args:
            query: 查询文本。
            docs: 融合层粗排 Top-N 候选。
            top_k: 精排后保留数量。

        Returns:
            (结果, 精排分) 列表，按精排分降序，长度 ≤ top_k。
        """
        ...
