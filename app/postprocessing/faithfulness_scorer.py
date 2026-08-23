"""
忠实度评分器。

使用 LLM 或 NLI 模型对答案-证据对打分。
"""

# --- 第三方库 ---
from langchain_core.language_models import BaseChatModel

# --- 本地模块 ---
from app.retrieval.dense_retriever import RetrievalResult


class FaithfulnessScorer:
    """忠实度评分器。

    评估生成答案与检索证据的一致性程度。
    """

    def __init__(
        self,
        llm: BaseChatModel,
        threshold: float = 0.7,
    ) -> None:
        """初始化忠实度评分器。

        Args:
            llm: 用于评分的 LLM 实例。
            threshold: 忠实度阈值，低于此值判定为不忠实。
        """
        self.llm = llm
        self.threshold = threshold

    async def score(
        self,
        answer: str,
        evidence: list[RetrievalResult],
    ) -> float:
        """计算答案的忠实度分数。

        Args:
            answer: 生成的答案文本。
            evidence: 检索证据列表。

        Returns:
            忠实度分数 [0.0, 1.0]。
        """
        # TODO: 使用 LLM 评估答案与证据的一致性
        raise NotImplementedError

    def is_faithful(self, score: float) -> bool:
        """判断忠实度分数是否通过阈值。

        Args:
            score: 忠实度分数。

        Returns:
            True 表示忠实度达标。
        """
        return score >= self.threshold
