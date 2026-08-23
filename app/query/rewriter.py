"""
查询改写器。

使用 HyDE 等策略将模糊/口语化查询改写为精确的检索查询。
"""

# --- 标准库 ---
from typing import Optional

# --- 第三方库 ---
from langchain_core.language_models import BaseChatModel


class QueryRewriter:
    """查询改写器。

    支持多种改写策略：HyDE（假设性文档嵌入）、直接改写、多轮上下文融合。
    """

    def __init__(self, llm: BaseChatModel) -> None:
        """初始化查询改写器。

        Args:
            llm: 用于查询改写的 LLM 实例（推荐使用轻量模型）。
        """
        self.llm = llm

    async def rewrite(
        self,
        query: str,
        strategy: str = "hyde",
        conversation_history: Optional[list[dict[str, str]]] = None,
    ) -> str:
        """改写用户查询。

        Args:
            query: 原始查询文本。
            strategy: 改写策略，可选 ``hyde`` / ``direct`` / ``contextual``。
            conversation_history: 多轮对话历史（用于上下文融合）。

        Returns:
            改写后的查询文本。
        """
        # TODO: 根据 strategy 选择改写方式
        # TODO: HyDE: 生成假设性答案，用答案去检索
        # TODO: direct: 直接优化查询表达
        # TODO: contextual: 融合对话历史改写查询
        raise NotImplementedError

    async def generate_hyde_answer(self, query: str) -> str:
        """生成假设性文档嵌入（HyDE）答案。

        让 LLM 生成一个假设性的答案段落，用该答案的向量去检索
        语义相近的真实文档。

        Args:
            query: 用户查询。

        Returns:
            假设性答案文本。
        """
        # TODO: 使用 Prompt 模板调用 LLM 生成假设性答案
        raise NotImplementedError
