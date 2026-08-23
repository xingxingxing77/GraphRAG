"""
上下文压缩器。

对 Reranker 保留的 chunks 进一步提取与查询相关的核心信息，减少 Token 消耗。
"""

# --- 第三方库 ---
from langchain_core.language_models import BaseChatModel

# --- 本地模块 ---
from app.retrieval.dense_retriever import RetrievalResult


class ContextCompressor:
    """上下文压缩器。

    使用 LLM 从检索结果中提取与查询最相关的关键信息，
    减少送入生成模型的 Token 数量。
    """

    def __init__(self, llm: BaseChatModel) -> None:
        """初始化上下文压缩器。

        Args:
            llm: 用于信息提取的 LLM 实例。
        """
        self.llm = llm

    async def compress(
        self,
        query: str,
        results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        """压缩检索结果的上下文。

        对每个 RetrievalResult 的 content 进行关键信息提取，
        替换原始的完整内容。

        Args:
            query: 用户查询。
            results: 待压缩的检索结果列表。

        Returns:
            压缩后的结果列表（content 字段被替换为摘要）。
        """
        # TODO: 对每个 result 使用 LLM 提取与 query 相关的关键句
        # TODO: 替换原始 content 为压缩后的文本
        raise NotImplementedError
