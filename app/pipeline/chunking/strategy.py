"""
分块策略接口与层级分块实现。

定义分块策略的抽象基类，并提供基于 Markdown 标题层级 +
字符级兜底的 HierarchicalChunkingStrategy 实现。
"""

# --- 标准库 ---
from abc import ABC, abstractmethod
from typing import Any

# --- 本地模块 ---
from app.pipeline.base import CleanedDocument, Chunk


class ChunkingStrategy(ABC):
    """分块策略抽象基类。

    所有分块策略（层级分块、语义分块、递归字符分块等）
    均实现此接口，提供统一的 split 方法。
    """

    @abstractmethod
    async def split(
        self,
        doc: CleanedDocument,
        config: dict[str, Any],
    ) -> list[Chunk]:
        """将清洗后文档切分为文档块列表。

        Args:
            doc: 清洗后的文档对象。
            config: 分块配置参数（如 chunk_size、chunk_overlap 等）。

        Returns:
            切分后的 Chunk 列表。
        """
        raise NotImplementedError


class HierarchicalChunkingStrategy(ChunkingStrategy):
    """层级分块策略。

    采用多级切分方式：
    1. 首先按 Markdown 标题层级切分（保留语义边界）。
    2. 对于超长的分块，退化为字符级兜底切分。

    这种策略兼顾了语义完整性和长度控制。

    Attributes:
        max_chunk_size: 单个 chunk 的最大字符数。
        chunk_overlap: 相邻 chunk 之间的重叠字符数。
    """

    def __init__(
        self,
        max_chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        """初始化 HierarchicalChunkingStrategy。

        Args:
            max_chunk_size: 单个 chunk 最大字符数，默认 500。
            chunk_overlap: chunk 重叠字符数，默认 50。
        """
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap

    async def split(
        self,
        doc: CleanedDocument,
        config: dict[str, Any],
    ) -> list[Chunk]:
        """执行层级分块。

        处理流程：
        1. 调用 MarkdownHeaderSplitter 按标题切分。
        2. 遍历结果，对超过 max_chunk_size 的块调用
           RecursiveCharacterSplitter 进行二次切分。
        3. 为每个 chunk 分配 position 和 title_path。

        Args:
            doc: 清洗后的文档对象。
            config: 配置参数，支持 key:
                - ``max_chunk_size``: 覆盖默认最大块大小。
                - ``chunk_overlap``: 覆盖默认重叠大小。

        Returns:
            切分后的 Chunk 列表。
        """
        # TODO: 1. 使用 MarkdownHeaderSplitter 按标题切分
        # TODO: 2. 遍历结果，对超长块调用 RecursiveCharacterSplitter
        # TODO: 3. 设置每个 chunk 的 position 和 title_path
        # TODO: 4. 返回 chunk 列表
        raise NotImplementedError
