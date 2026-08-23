"""
元数据增强器（架构 P5 元数据增强 · 单元 2.2）。

为文档块补全统一 metadata 键（架构 §3.2 / MetadataKeys）：
source / category / doc_type / created_at / lang / quality_score，
并基于来源路径推断 doc_type 与 category（HowToCook 语料目录结构）。
"""

# --- 标准库 ---
from datetime import datetime, timezone

# --- 本地模块 ---
from app.core.models import Chunk, EnrichedChunk, MetadataKeys
from app.pipeline.enrichment.semantic_enricher import SemanticEnricher

# doc_type 推断：来源路径片段 → Collection 划分依据（04 §3.1 rag_<用途>）
_DOC_TYPE_HINTS: tuple[tuple[str, str], ...] = (
    ("/dishes/", "recipes"),
    ("\\dishes\\", "recipes"),
    ("/tips/", "tips"),
    ("\\tips\\", "tips"),
)


class MetadataEnricher:
    """元数据增强器。

    Attributes:
        default_category: 无法推断时的默认分类。
        default_doc_type: 无法推断时的默认文档类型。
    """

    def __init__(
        self,
        default_category: str = "uncategorized",
        default_doc_type: str = "knowledge",
    ) -> None:
        """初始化 MetadataEnricher。

        Args:
            default_category: 默认分类名称。
            default_doc_type: 默认文档类型（knowledge 兜底）。
        """
        self.default_category = default_category
        self.default_doc_type = default_doc_type

    def enrich(
        self,
        chunk: Chunk,
        source_path: str,
        quality_score: float | None = None,
        lang: str | None = None,
    ) -> EnrichedChunk:
        """为单个 chunk 补全元数据并构建 EnrichedChunk。

        Args:
            chunk: 待增强的文档块。
            source_path: 文档来源路径（RawDocument.source_path）。
            quality_score: P3 门控质量分（透传）。
            lang: 语言标识（可选）。

        Returns:
            元数据增强后的 EnrichedChunk。
        """
        doc_type = self.infer_doc_type(source_path)
        category = self.infer_category(source_path)
        metadata = {
            **chunk.metadata,
            MetadataKeys.DOC_ID: chunk.doc_id,
            MetadataKeys.CHUNK_ID: chunk.chunk_id,
            MetadataKeys.SOURCE: source_path,
            MetadataKeys.DOC_TYPE: doc_type,
            MetadataKeys.CATEGORY: category,
            MetadataKeys.TITLE_PATH: list(chunk.title_path),
            MetadataKeys.CREATED_AT: datetime.now(timezone.utc).isoformat(),
        }
        if quality_score is not None:
            metadata[MetadataKeys.QUALITY_SCORE] = quality_score
        if lang:
            metadata[MetadataKeys.LANG] = lang

        enriched_chunk = EnrichedChunk(
            chunk=chunk.model_copy(update={"metadata": metadata}),
        )
        return enriched_chunk

    def infer_doc_type(self, source_path: str) -> str:
        """从来源路径推断 doc_type（Collection 划分依据）。

        Args:
            source_path: 来源路径。

        Returns:
            recipes / tips / knowledge 之一。
        """
        lowered = source_path.lower()
        for hint, doc_type in _DOC_TYPE_HINTS:
            if hint in lowered:
                return doc_type
        return self.default_doc_type

    def infer_category(self, source_path: str) -> str:
        """从来源路径推断业务分类。

        HowToCook 结构：dishes/<category>/... 与 tips/<category>/...，
        取 dishes|tips 之后的第一段目录名作为 category。

        Args:
            source_path: 来源路径。

        Returns:
            分类名（无法推断时返回 default_category）。
        """
        normalized = source_path.replace("\\", "/").lower()
        for marker in ("/dishes/", "/tips/"):
            if marker in normalized:
                rest = normalized.split(marker, 1)[1]
                segment = rest.split("/", 1)[0].strip()
                if segment:
                    return segment
        return self.default_category


async def enrich_chunks(
    chunks: list[Chunk],
    source_path: str,
    quality_score: float | None = None,
    lang: str | None = None,
) -> list[EnrichedChunk]:
    """P5 增强编排入口：元数据补全 + 关键词提取（单元 2.2）。

    Args:
        chunks: 分块列表（P4 输出）。
        source_path: 文档来源路径。
        quality_score: P3 门控质量分。
        lang: 语言标识。

    Returns:
        EnrichedChunk 列表（metadata/keywords 已填充）。
    """
    meta_enricher = MetadataEnricher()
    semantic_enricher = SemanticEnricher()
    results: list[EnrichedChunk] = []
    for chunk in chunks:
        enriched = meta_enricher.enrich(
            chunk, source_path, quality_score=quality_score, lang=lang
        )
        enriched = await semantic_enricher.enrich(
            enriched, category=str(enriched.chunk.metadata.get(MetadataKeys.CATEGORY, ""))
        )
        results.append(enriched)
    return results
