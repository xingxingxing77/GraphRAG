"""
子查询分解器。

将复杂问题拆解为多个独立的子查询，并行检索后合并结果。
"""

# --- 第三方库 ---
from langchain_core.language_models import BaseChatModel


class QueryDecomposer:
    """子查询分解器。

    将复杂的多跳/对比型查询拆解为 2-4 个独立的子查询，
    每个子查询可独立检索，最终合并结果。
    """

    def __init__(self, llm: BaseChatModel) -> None:
        """初始化子查询分解器。

        Args:
            llm: 用于分解查询的 LLM 实例。
        """
        self.llm = llm

    async def decompose(self, query: str) -> list[str]:
        """将复杂查询分解为子查询列表。

        Args:
            query: 原始复杂查询。

        Returns:
            子查询字符串列表（2-4 个）。如果查询足够简单，
            返回包含原始查询的单元素列表。
        """
        # TODO: 使用 LLM 判断查询复杂度并分解
        # TODO: 如果查询简单，直接返回 [query]
        raise NotImplementedError

    async def should_decompose(self, query: str) -> bool:
        """判断查询是否需要分解。

        Args:
            query: 用户查询。

        Returns:
            True 表示需要分解（多跳/对比型），False 表示不需要。
        """
        # TODO: 使用规则或 LLM 判断是否需要分解
        raise NotImplementedError
