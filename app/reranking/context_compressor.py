"""
上下文压缩器（架构 L5 · J11 可插拔策略 · 单元 4.2）。

三策略压缩接口（策略经 retrieval.compression_strategy 配置切换，不写死）：
- ``none``：直通（默认档，不压缩）；
- ``extractive``：抽取式——按查询词重合度挑核心句（无 LLM）；
- ``llm_extract``：LLM 提取与查询相关的核心句（deep 档默认）。
"""

# --- 标准库 ---
import logging
import re
from typing import Awaitable, Callable, Protocol, runtime_checkable

# --- 本地模块 ---
from app.core.models import RetrievalResult

logger = logging.getLogger(__name__)

# 句子切分正则（中文句读 + 换行）
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?\n])")


@runtime_checkable
class CompressionStrategy(Protocol):
    """压缩策略协议（J11 可插拔接口）。"""

    name: str

    async def compress(
        self, query: str, results: list[RetrievalResult]
    ) -> list[RetrievalResult]:
        """压缩检索结果内容。

        Args:
            query: 查询文本。
            results: 精排后的检索结果。

        Returns:
            content 被压缩后的结果列表（顺序与数量不变）。
        """
        ...


class NoneStrategy:
    """直通策略（不压缩）。"""

    name: str = "none"

    async def compress(
        self, query: str, results: list[RetrievalResult]
    ) -> list[RetrievalResult]:
        """原样返回。

        Args:
            query: 查询文本（未使用）。
            results: 检索结果。

        Returns:
            原结果列表。
        """
        return results


class ExtractiveStrategy:
    """抽取式压缩（查询词重合度挑核心句，无 LLM 依赖）。"""

    name: str = "extractive"

    def __init__(self, max_sentences: int = 3) -> None:
        """初始化抽取式策略。

        Args:
            max_sentences: 每条结果保留的最大句数。
        """
        self.max_sentences = max_sentences

    async def compress(
        self, query: str, results: list[RetrievalResult]
    ) -> list[RetrievalResult]:
        """按句与查询的字符重合度挑 Top 句。

        Args:
            query: 查询文本。
            results: 检索结果。

        Returns:
            content 替换为核心句拼接的结果列表。
        """
        query_chars = set(query)
        compressed: list[RetrievalResult] = []
        for r in results:
            sentences = [s.strip() for s in _SENTENCE_SPLIT.split(r.content) if s.strip()]
            if len(sentences) <= 1:
                compressed.append(r)
                continue
            scored = sorted(
                sentences,
                key=lambda s: len(query_chars & set(s)) / max(1, len(s)),
                reverse=True,
            )
            kept = scored[: self.max_sentences]
            # 保持原文顺序
            kept_set = set(kept)
            ordered = [s for s in sentences if s in kept_set]
            compressed.append(r.model_copy(update={"content": "".join(ordered)}))
        return compressed


class LLMExtractStrategy:
    """LLM 提取压缩（deep 档默认；提取函数注入，LLM 接入在阶段 5）。"""

    name: str = "llm_extract"

    def __init__(
        self,
        extract_fn: Callable[[str, str], Awaitable[str]],
    ) -> None:
        """初始化 LLM 提取策略。

        Args:
            extract_fn: 异步提取函数，签名 (query, content) -> 压缩文本。
        """
        self._extract_fn = extract_fn

    async def compress(
        self, query: str, results: list[RetrievalResult]
    ) -> list[RetrievalResult]:
        """逐条调 LLM 提取核心句（单条失败回退原文）。

        Args:
            query: 查询文本。
            results: 检索结果。

        Returns:
            content 替换为提取文本的结果列表。
        """
        compressed: list[RetrievalResult] = []
        for r in results:
            try:
                extracted = await self._extract_fn(query, r.content)
                content = extracted.strip() or r.content
            except Exception as exc:  # noqa: BLE001 - 单条失败回退原文
                logger.warning("llm_extract 单条失败，回退原文: %s", exc)
                content = r.content
            compressed.append(r.model_copy(update={"content": content}))
        return compressed


def create_strategy(
    name: str,
    extract_fn: Callable[[str, str], Awaitable[str]] | None = None,
) -> CompressionStrategy:
    """按配置名创建压缩策略（J11：不写死）。

    Args:
        name: 策略名（none | extractive | llm_extract）。
        extract_fn: llm_extract 所需的提取函数（缺失时回退 none 并告警）。

    Returns:
        压缩策略实例。
    """
    if name == "extractive":
        return ExtractiveStrategy()
    if name == "llm_extract":
        if extract_fn is None:
            logger.warning("llm_extract 缺少 extract_fn，回退 none 策略")
            return NoneStrategy()
        return LLMExtractStrategy(extract_fn)
    return NoneStrategy()


class ContextCompressor:
    """上下文压缩器（策略分发入口）。

    Attributes:
        strategy: 当前压缩策略。
    """

    def __init__(self, strategy: CompressionStrategy | None = None) -> None:
        """初始化压缩器。

        Args:
            strategy: 压缩策略，缺省 NoneStrategy。
        """
        self.strategy: CompressionStrategy = strategy or NoneStrategy()

    async def compress(
        self,
        query: str,
        results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        """压缩检索结果的上下文。

        Args:
            query: 用户查询。
            results: 待压缩的检索结果列表。

        Returns:
            压缩后的结果列表（content 字段按策略处理）。
        """
        return await self.strategy.compress(query, results)
