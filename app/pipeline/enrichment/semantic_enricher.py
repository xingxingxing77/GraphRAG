"""
语义增强器。

通过 LLM 为文档块生成语义附加信息，如关键词提取、
摘要生成、假设性问题等，提升检索召回率。
"""

# --- 标准库 ---
from typing import Any, Protocol

# --- 本地模块 ---
from app.pipeline.base import Chunk, EnrichedChunk


class LLMServiceLike(Protocol):
    """LLM 服务的协议接口（用于类型提示）。"""

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        """调用 LLM 生成文本。"""
        ...


class SemanticEnricher:
    """语义增强器。

    利用 LLM 为文档块生成语义附加信息，
    支持以下增强方法（可按需组合）：

    - ``keyword_extract``：提取关键词列表。
    - ``summary_generate``：生成简短摘要。
    - ``hypothetical_questions``：生成假设性问题列表（HyDE 思路）。

    生成结果存储在 EnrichedChunk.metadata 中。

    Attributes:
        llm_service: LLM 服务实例。
        default_methods: 默认启用的增强方法列表。
    """

    # 支持的增强方法
    SUPPORTED_METHODS: set[str] = {
        "keyword_extract",
        "summary_generate",
        "hypothetical_questions",
    }

    def __init__(
        self,
        llm_service: LLMServiceLike,
        default_methods: list[str] | None = None,
    ) -> None:
        """初始化 SemanticEnricher。

        Args:
            llm_service: LLM 服务实例，需提供 generate 方法。
            default_methods: 默认启用的增强方法列表，
                默认 ["keyword_extract", "summary_generate"]。

        Raises:
            ValueError: 指定的方法不在 SUPPORTED_METHODS 中。
        """
        self.llm_service = llm_service
        self.default_methods = default_methods or [
            "keyword_extract",
            "summary_generate",
        ]

    async def enrich(
        self,
        chunk: Chunk,
        methods: list[str] | None = None,
    ) -> EnrichedChunk:
        """对单个 chunk 执行语义增强。

        依次执行 methods 中指定的增强方法，
        将结果写入 EnrichedChunk.metadata。

        Args:
            chunk: 待增强的文档块。
            methods: 要执行的增强方法列表，默认使用 self.default_methods。

        Returns:
            语义增强后的 EnrichedChunk。

        Raises:
            ValueError: 指定的方法不被支持。
        """
        # TODO: 1. 校验 methods 中的方法名是否合法
        # TODO: 2. 对每个方法调用对应的 _xxx 内部方法
        # TODO: 3. 将结果合并到 metadata
        # TODO: 4. 构建并返回 EnrichedChunk
        raise NotImplementedError

    async def _keyword_extract(self, text: str) -> list[str]:
        """使用 LLM 提取关键词。

        Args:
            text: chunk 文本内容。

        Returns:
            关键词字符串列表。
        """
        # TODO: 构建 prompt，调用 llm_service.generate，解析结果
        raise NotImplementedError

    async def _summary_generate(self, text: str) -> str:
        """使用 LLM 生成摘要。

        Args:
            text: chunk 文本内容。

        Returns:
            摘要字符串。
        """
        # TODO: 构建 prompt，调用 llm_service.generate
        raise NotImplementedError

    async def _hypothetical_questions(self, text: str) -> list[str]:
        """使用 LLM 生成假设性问题。

        Args:
            text: chunk 文本内容。

        Returns:
            假设性问题字符串列表。
        """
        # TODO: 构建 prompt，调用 llm_service.generate，按行解析
        raise NotImplementedError
