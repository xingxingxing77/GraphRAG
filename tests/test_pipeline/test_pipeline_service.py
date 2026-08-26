"""GAP-A3 索引管道编排器测试（PipelineService）。

验证端到端链：RawDocument → parse → clean → chunk → enrich → 三索引
（三 indexer 以内存替身断言被调用与统计口径）。
"""

# --- 标准库 ---
import hashlib
from datetime import datetime, timezone

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import EnrichedChunk, RawDocument
from app.pipeline.chunking.strategy import chunk_document
from app.pipeline.cleaning.pipeline import CleaningPipeline
from app.pipeline.config import ChunkingConfig
from app.pipeline.indexing.pipeline_service import PipelineService
from app.pipeline.parsing.router import FormatRouter


class FakeVectorIndexer:
    """Qdrant 向量索引器内存替身。"""

    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str]] = []

    async def index(self, chunks: list[EnrichedChunk], source: str, doc_type: str) -> int:
        self.calls.append((len(chunks), source, doc_type))
        return len(chunks)


class FakeGraphWriter:
    """Neo4j 图谱写入器内存替身。"""

    def __init__(self) -> None:
        self.writes: list[int] = []

    async def write_enriched_chunks(self, chunks: list[EnrichedChunk]) -> None:
        self.writes.append(len(chunks))


class FakeESSyncer:
    """ES 全文同步器内存替身。"""

    def __init__(self) -> None:
        self.syncs: list[int] = []

    async def sync_chunks(self, docs: list[dict]) -> int:
        self.syncs.append(len(docs))
        return len(docs)


def _raw_doc(doc_id: str, source: str, text: str) -> RawDocument:
    return RawDocument(
        doc_id=doc_id,
        source_path=source,
        raw_bytes=text.encode("utf-8"),
        mime_type="text/markdown",
        timestamp=datetime.now(timezone.utc),
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def _service(vector, graph, es) -> PipelineService:
    return PipelineService(
        format_router=FormatRouter(),
        cleaning_pipeline=CleaningPipeline(),
        chunking_cfg=ChunkingConfig(),
        vector_indexer=vector,
        graph_writer=graph,
        es_syncer=es,
    )


@pytest.mark.asyncio
async def test_pipeline_indexes_document_end_to_end() -> None:
    """单个 Markdown 文档走完整管线并命中三索引。"""
    vector = FakeVectorIndexer()
    graph = FakeGraphWriter()
    es = FakeESSyncer()
    svc = _service(vector, graph, es)
    doc = _raw_doc(
        "doc-recipes-1",
        "menu/HowToCook/dishes/aquatic/清蒸鲈鱼.md",
        "# 清蒸鲈鱼\n\n## 食材\n\n鲈鱼一条约六百克，姜片若干，葱段若干，蒸鱼豉油两勺，食用油一勺。\n\n## 做法\n\n将鲈鱼去鳞去鳃去内脏洗净，鱼身两侧各划两刀便于入味。\n盘中铺姜片与葱段垫底，放上鲈鱼，鱼腹内也塞入姜葱。\n蒸锅加水烧开后放入鱼盘，大火隔水蒸八分钟出锅。\n倒掉盘中腥水，拣去姜葱，鱼身铺新切的葱丝。\n淋上两勺蒸鱼豉油，烧一勺热油浇在葱丝上激出香味即可上桌。",
    )
    stats = await svc.index_documents([doc])

    assert stats.documents == 1
    assert stats.chunks >= 1
    assert stats.vector_points == stats.chunks
    assert stats.fulltext_written == stats.chunks
    assert vector.calls and vector.calls[0][0] == stats.chunks
    assert graph.writes == [stats.chunks]
    assert es.syncs == [stats.chunks]


@pytest.mark.asyncio
async def test_pipeline_skips_failed_document() -> None:
    """单文档解析失败（非法格式）仅记跳过，不抛错阻塞整批。"""
    vector = FakeVectorIndexer()
    graph = FakeGraphWriter()
    es = FakeESSyncer()
    svc = _service(vector, graph, es)
    bad = _raw_doc("doc-bad", "x.unknown", "内容")
    bad = bad.model_copy(update={"mime_type": "application/octet-stream"})

    stats = await svc.index_documents([bad])
    assert stats.documents == 0
    assert stats.failed == 1
    assert vector.calls == []
