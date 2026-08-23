"""
元数据增强器。

为文档块添加丰富的元数据字段，如来源、类别、文档类型、
创建时间等，便于下游检索和过滤。
"""

# --- 标准库 ---
from datetime import datetime, timezone
from typing import Any

# --- 本地模块 ---
from app.pipeline.base import Chunk, EnrichedChunk


class MetadataEnricher:
    """元数据增强器。

    从 Chunk 和文档来源信息中提取元数据，
    构建包含丰富属性的 EnrichedChunk。

    注入的元数据字段包括：
    - ``source``: 文档来源路径或 URL。
    - ``category``: 文档分类（如 "菜谱"、"技巧"）。
    - ``doc_type``: 文档类型（如 "markdown"、"html"、"pdf"）。
    - ``created_at``: 文档创建/采集时间。
    - ``chunk_index``: chunk 在原文档中的位置序号。

    Attributes:
        default_category: 无法推断时的默认分类。
    """

    def __init__(self, default_category: str = "uncategorized") -> None:
        """初始化 MetadataEnricher。

        Args:
            default_category: 默认分类名称。
        """
        self.default_category = default_category

    def enrich(self, chunk: Chunk) -> EnrichedChunk:
        """为单个 chunk 添加元数据。

        从 chunk 的 metadata 和 position 中提取信息，
        补充 source、category、doc_type、created_at 等字段。

        Args:
            chunk: 待增强的文档块。

        Returns:
            元数据增强后的 EnrichedChunk。
        """
        # TODO: 1. 从 chunk.metadata 提取 source、doc_type
        # TODO: 2. 推断 category（基于目录结构或文件路径）
        # TODO: 3. 设置 created_at = datetime.now(timezone.utc).isoformat()
        # TODO: 4. 复制 chunk.content 和已有 metadata
        # TODO: 5. 构建并返回 EnrichedChunk
        raise NotImplementedError
