"""
分块策略接口与层级分块实现（架构 P4 · H3 · 单元 2.1）。

多级分块策略：
1. 第一级结构分块——按 Markdown 标题层级切分，保留 title_path；
2. 异常判定（结果为空 / 仅 1 块 / 单块超 800 字符）→ 第二级字符级兜底；
3. 节内超长段同样走递归字符切分（继承 title_path）；
4. min_chunk_size 过滤 + 上下文保留（前缀注入 / 父子引用）。

计量单位统一为字符（H3）：chunk_size=500 ≈ 350-500 token，
在 BGE-M3 的 8192 窗口内。
"""

# --- 标准库 ---
from abc import ABC, abstractmethod
from typing import Any

# --- 本地模块 ---
from app.core.models import Chunk, CleanedDocument, MetadataKeys, PositionMeta
from app.pipeline.chunking.context_preserver import ContextPreserver
from app.pipeline.chunking.markdown_splitter import HeaderSection, MarkdownHeaderSplitter
from app.pipeline.chunking.recursive_splitter import RecursiveCharacterSplitter
from app.pipeline.config import ChunkingConfig, load_pipeline_config

# 第一级结果异常判定阈值（架构 P4：单块超 800 字符即转兜底）
_FALLBACK_TRIGGER_SIZE = 800


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
            切分后的 Chunk 列表（chunk_id/seq/position 已赋值）。
        """
        raise NotImplementedError


class HierarchicalChunkingStrategy(ChunkingStrategy):
    """层级分块策略（结构优先 + 字符兜底）。

    Attributes:
        header_splitter: 第一级标题切分器。
        recursive_splitter: 第二级递归字符切分器。
        min_chunk_size: 最短块长（字符），过短的块被过滤。
        max_chunk_size: 最大块长（字符），硬约束。
        fallback_trigger_size: 单块超长兜底触发阈值（默认 800）。
    """

    def __init__(
        self,
        header_splitter: MarkdownHeaderSplitter | None = None,
        recursive_splitter: RecursiveCharacterSplitter | None = None,
        min_chunk_size: int = 50,
        max_chunk_size: int = 1500,
        fallback_trigger_size: int = _FALLBACK_TRIGGER_SIZE,
    ) -> None:
        """初始化层级分块策略。

        Args:
            header_splitter: 标题切分器（缺省 1-4 级）。
            recursive_splitter: 递归字符切分器（缺省 500/80）。
            min_chunk_size: 最短块长过滤阈值。
            max_chunk_size: 最大块长硬约束。
            fallback_trigger_size: 单块超长兜底触发阈值。
        """
        self.header_splitter = header_splitter or MarkdownHeaderSplitter()
        self.recursive_splitter = recursive_splitter or RecursiveCharacterSplitter()
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.fallback_trigger_size = fallback_trigger_size

    async def split(
        self,
        doc: CleanedDocument,
        config: dict[str, Any],
    ) -> list[Chunk]:
        """执行层级分块。

        Args:
            doc: 清洗后的文档对象。
            config: 运行时覆盖参数（当前未使用，配置经构造注入）。

        Returns:
            Chunk 列表：chunk_id=f"{doc_id}-{seq}"，position 精确到字符，
            metadata 含 doc_id/chunk_id/title_path。
        """
        text = doc.text
        sections = self.header_splitter.split(text)

        if self._is_anomalous(sections, text):
            # 全文字符级兜底（空标题树 / 仅 1 块 / 单块超长）；
            # 唯一节的 title_path 仍予保留（兜底只改切分方式，不丢上下文）
            base_path = sections[0].title_path if sections else []
            raw_spans: list[tuple[list[str], int, int]] = [
                (list(base_path), s, e)
                for s, e in self.recursive_splitter.split_spans(text)
            ]
        else:
            raw_spans = []
            for sec in sections:
                if len(sec.text) > self.recursive_splitter.chunk_size:
                    # 节内超长：递归切分并继承 title_path
                    for s, e in self.recursive_splitter.split_spans(sec.text):
                        raw_spans.append(
                            (
                                sec.title_path,
                                sec.start_offset + s,
                                sec.start_offset + e,
                            )
                        )
                else:
                    raw_spans.append(
                        (sec.title_path, sec.start_offset, sec.end_offset)
                    )

        chunks = self._build_chunks(doc, text, raw_spans)
        # min_chunk_size 过滤（过短的块无意义，架构 P4）
        return [c for c in chunks if len(c.content.strip()) >= self.min_chunk_size]

    def _is_anomalous(self, sections: list[HeaderSection], text: str) -> bool:
        """第一级结果异常判定（架构 P4 流程图）。

        Args:
            sections: 标题切分结果。
            text: 全文。

        Returns:
            True 表示需整篇字符级兜底。
        """
        if not sections:
            return True
        if len(sections) == 1 and len(text) > self.fallback_trigger_size:
            return True
        return any(len(s.text) > self.fallback_trigger_size and len(sections) == 1 for s in sections)

    def _build_chunks(
        self,
        doc: CleanedDocument,
        text: str,
        spans: list[tuple[list[str], int, int]],
    ) -> list[Chunk]:
        """由偏移区间序列构建 Chunk 列表。

        Args:
            doc: 源文档（取 doc_id 与 quality_score）。
            text: 全文（内容切片依据）。
            spans: [(title_path, start, end), ...]。

        Returns:
            Chunk 列表（seq 从 0 递增，未做 min 过滤）。
        """
        chunks: list[Chunk] = []
        for seq, (title_path, start, end) in enumerate(spans):
            chunk_id = f"{doc.doc_id}-{seq}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    doc_id=doc.doc_id,
                    seq=seq,
                    content=text[start:end],
                    title_path=list(title_path),
                    position=PositionMeta(start_char=start, end_char=end),
                    metadata={
                        MetadataKeys.DOC_ID: doc.doc_id,
                        MetadataKeys.CHUNK_ID: chunk_id,
                        MetadataKeys.TITLE_PATH: list(title_path),
                        MetadataKeys.QUALITY_SCORE: doc.quality_score,
                    },
                )
            )
        return chunks


def build_chunking_strategy(cfg: ChunkingConfig) -> HierarchicalChunkingStrategy:
    """按配置构建层级分块策略。

    Args:
        cfg: 分块配置（pipeline_config.yaml chunking 段）。

    Returns:
        HierarchicalChunkingStrategy 实例。
    """
    second = cfg.second_level
    return HierarchicalChunkingStrategy(
        header_splitter=MarkdownHeaderSplitter(cfg.first_level.header_levels()),
        recursive_splitter=RecursiveCharacterSplitter(
            chunk_size=second.chunk_size,
            chunk_overlap=second.chunk_overlap,
            separators=second.separators,
        ),
        min_chunk_size=cfg.constraints.min_chunk_size,
        max_chunk_size=cfg.constraints.max_chunk_size,
    )


async def chunk_document(
    doc: CleanedDocument, cfg: ChunkingConfig | None = None
) -> list[Chunk]:
    """分块编排入口：策略切分 + 上下文保留（单元 2.1）。

    Args:
        doc: 清洗后的文档。
        cfg: 分块配置（缺省从 pipeline_config.yaml 加载）。

    Returns:
        最终 Chunk 列表（已注入 title_path 前缀与 parent_ref）。
    """
    config = cfg or load_pipeline_config().pipeline.chunking
    strategy = build_chunking_strategy(config)
    chunks = await strategy.split(doc, {})

    preserver = ContextPreserver()
    if config.context_preservation.prefix_injection:
        chunks = preserver.inject_title_path(chunks)
    if config.context_preservation.parent_ref:
        chunks = preserver.add_parent_ref(chunks, doc.doc_id)
    return chunks
