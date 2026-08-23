"""
幻觉检测器。

检查生成答案中的事实是否都能在检索证据中找到支撑。
"""

# --- 第三方库 ---
from langchain_core.language_models import BaseChatModel

# --- 本地模块 ---
from app.retrieval.dense_retriever import RetrievalResult


class HallucinationDetector:
    """幻觉检测器。

    使用 LLM 或 NLI 模型检查生成答案与检索证据的一致性，
    识别答案中不受证据支撑的"幻觉"内容。
    """

    def __init__(self, llm: BaseChatModel) -> None:
        """初始化幻觉检测器。

        Args:
            llm: 用于检测的 LLM 实例。
        """
        self.llm = llm

    async def detect(
        self,
        answer: str,
        evidence: list[RetrievalResult],
    ) -> HallucinationReport:
        """检测答案中的幻觉。

        Args:
            answer: 生成的答案文本。
            evidence: 检索证据列表。

        Returns:
            HallucinationReport: 检测报告。
        """
        # TODO: 构建检测 Prompt
        # TODO: 调用 LLM 进行幻觉检测
        # TODO: 返回检测报告
        raise NotImplementedError


class HallucinationReport:
    """幻觉检测报告。

    Attributes:
        has_hallucination: 是否检测到幻觉。
        confidence: 检测置信度。
        unsupported_claims: 不受支撑的声明列表。
    """

    def __init__(
        self,
        has_hallucination: bool = False,
        confidence: float = 1.0,
        unsupported_claims: list[str] | None = None,
    ) -> None:
        self.has_hallucination = has_hallucination
        self.confidence = confidence
        self.unsupported_claims = unsupported_claims or []
