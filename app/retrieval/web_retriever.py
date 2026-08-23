"""
Web 搜索工具。

使用 Tavily/DuckDuckGo 进行外部知识搜索，作为兜底检索。
"""

# --- 标准库 ---
from typing import Optional

# --- 本地模块 ---
from app.retrieval.dense_retriever import RetrievalResult


class WebRetriever:
    """Web 搜索检索器。

    当内部知识库检索结果不足时，通过外部搜索引擎获取补充信息。
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        """初始化 Web 检索器。

        Args:
            api_key: Tavily API Key。为 None 时使用 DuckDuckGo。
        """
        self.api_key = api_key

    async def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """执行 Web 搜索。

        Args:
            query: 搜索查询。
            top_k: 返回数量。

        Returns:
            检索结果列表（source="web"）。
        """
        # TODO: 如果有 api_key，使用 Tavily API
        # TODO: 否则使用 DuckDuckGo 搜索
        # TODO: 格式化结果为 RetrievalResult 列表
        raise NotImplementedError
