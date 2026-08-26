"""
索引管道编排器（GAP-A3 · 架构 P2-P6）。

串起「采集产物 RawDocument → P2 解析 → P3 清洗 → P4 分块 →
P5 增强（元数据+关键词，实体/关系经 graph_construction 在 LLM
可用时注入）→ 三索引写入（Qdrant 向量 / Neo4j 图 / ES 全文）」。

这是「系统能吃文档」的核心编排入口：此前各层（parse/clean/chunk/
enrich）与三 indexer 均可真实现但无生产调用方，本模块将其串成
端到端可脱离 admin 逐段手工调用的自动路径。

可靠性：单文档解析/清洗失败仅记日志跳过，不阻塞整批（M3/D5）。
"""

# --- 标准库 ---
import logging
from dataclasses import dataclass, field
from typing import Any

# --- 本地模块 ---
from app.core.models import EnrichedChunk, MetadataKeys, RawDocument
from app.pipeline.chunking.strategy import chunk_document
from app.pipeline.config import ChunkingConfig
from app.pipeline.cleaning.pipeline import CleaningPipeline
from app.pipeline.enrichment.metadata_enricher import enrich_chunks
from app.pipeline.graph_construction.graph_writer import GraphWriter
from app.pipeline.indexing.fulltext_indexer import ESSyncer
from app.pipeline.indexing.vector_indexer import VectorIndexer
from app.pipeline.parsing.router import FormatRouter

logger = logging.getLogger(__name__)


@dataclass
class IndexStats:
    """一次索引编排的统计口径（供 admin/脚本日志）。

    Attributes:
        documents: 处理文档数。
        chunks: 产出块数。
        vector_points: 向量写入点数。
        fulltext_written: 全文写入条数。
        failed: 失败文档数（跳过的解析/清洗失败）。
    """

    documents: int = 0
    chunks: int = 0
    vector_points: int = 0
    fulltext_written: int = 0
    failed: int = 0


def chunk_to_es_doc(chunk: EnrichedChunk) -> dict[str, Any]:
    """EnrichedChunk → ES rag_chunks 文档（_id = chunk_id，04 §6）。"""
    meta = chunk.chunk.metadata
    return {
        "chunk_id": chunk.chunk.chunk_id,
        "doc_id": chunk.chunk.doc_id,
        "content": chunk.chunk.content,
        "title_path": list(chunk.chunk.title_path),
        "created_at": meta.get(MetadataKeys.CREATED_AT, ""),
    }


class PipelineService:
    """端到端索引编排器（GAP-A3）。

    Attributes:
        format_router: 格式解析路由器（P2）。
        cleaning_pipeline: 清洗规则链（P3）。
        chunking_cfg: 分块配置（P4）。
        vector_indexer: Qdrant 向量索引器（P6）。
        graph_writer: Neo4j 图谱写入器（G4）。
        es_syncer: ES 全文同步器（J6）。
    """

    def __init__(
        self,
        format_router: FormatRouter,
        cleaning_pipeline: CleaningPipeline,
        chunking_cfg: ChunkingConfig,
        vector_indexer: VectorIndexer,
        graph_writer: GraphWriter,
        es_syncer: ESSyncer,
    ) -> None:
        self.format_router = format_router
        self.cleaning_pipeline = cleaning_pipeline
        self.chunking_cfg = chunking_cfg
        self.vector_indexer = vector_indexer
        self.graph_writer = graph_writer
        self.es_syncer = es_syncer

    async def process_document(self, raw: RawDocument) -> list[EnrichedChunk]:
        """单文档 P2→P3→P4→P5 管线，产出增强块列表。"""
        parsed = await self.format_router.parse(raw)
        cleaned = await self.cleaning_pipeline.run(parsed)
        chunks = await chunk_document(cleaned, self.chunking_cfg)
        return await enrich_chunks(chunks, raw.source_path, cleaned.quality_score)

    async def clear_all(self) -> None:
        """全量重建前置：清空三存储既有索引数据（BUG-E）。

        范围：仅业务集合（Qdrant rag_* 排除 rag_cache/rag_episodic 记忆层）、
        Neo4j Chunk/Document 节点、ES rag_chunks 全文索引；不触碰社区/实体
        派生数据与记忆层。任一存储清空失败仅记日志继续（降级不阻断重建，
        M3/D5）。
        """
        # ① Qdrant：清空业务向量集合（记忆层集合跳过）
        try:
            for name in await self.vector_indexer.db_client.list_collections():
                if name.startswith("rag_") and name not in ("rag_cache", "rag_episodic"):
                    deleted = await self.vector_indexer.db_client.clear_collection(name)
                    logger.info("Qdrant 清空集合 %s：%d points", name, deleted)
        except Exception as exc:  # noqa: BLE001 - 清空失败不阻断重建
            logger.warning("Qdrant 全量清空失败: %s", exc)

        # ② Neo4j：清空 Chunk / Document 节点（级联 MENTIONS/REL 边）
        for cypher in (
            "MATCH (c:Chunk) DETACH DELETE c",
            "MATCH (d:Document) DETACH DELETE d",
        ):
            try:
                await self.graph_writer.client.execute_cypher(cypher, {})
            except Exception as exc:  # noqa: BLE001
                logger.warning("Neo4j 全量清空失败（%s）: %s", cypher[:20], exc)

        # ③ ES：清空 rag_chunks 全文索引
        try:
            from app.db.es_client import CHUNKS_ALIAS

            deleted = await self.es_syncer.es.clear_alias(CHUNKS_ALIAS)
            logger.info("ES 清空 %s：%d docs", CHUNKS_ALIAS, deleted)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ES 全量清空失败: %s", exc)

    async def index_documents(self, documents: list[RawDocument]) -> IndexStats:
        """对一批 RawDocument 执行管线并三索引入库。

        每个文档独立容错：单文档失败仅记日志跳过（降级不抛错）。

        Args:
            documents: 采集层产出的原始文档列表。

        Returns:
            IndexStats: 本次编排统计。
        """
        stats = IndexStats()
        for raw in documents:
            try:
                enriched = await self.process_document(raw)
            except Exception as exc:  # noqa: BLE001 - 单文档失败不阻塞整批
                logger.warning("文档编排失败（%s）: %s", raw.source_path, exc)
                stats.failed += 1
                continue
            if not enriched:
                continue
            doc_type = str(
                enriched[0].chunk.metadata.get(MetadataKeys.DOC_TYPE, "knowledge")
            )
            # 三索引写入与 P2-P5 同属单文档容错范围：任一存储写入失败
            # 仅记日志跳过该文档，不阻塞整批（M3/D5）。
            try:
                vector_points = await self.vector_indexer.index(
                    enriched, raw.source_path, doc_type
                )
                await self.graph_writer.write_enriched_chunks(enriched)
                fulltext_written = await self.es_syncer.sync_chunks(
                    [chunk_to_es_doc(c) for c in enriched]
                )
            except Exception as exc:  # noqa: BLE001 - 单文档索引失败不阻塞整批
                logger.warning("三索引入库失败（%s）: %s", raw.source_path, exc)
                stats.failed += 1
                continue
            stats.documents += 1
            stats.chunks += len(enriched)
            stats.vector_points += vector_points
            stats.fulltext_written += fulltext_written
        logger.info(
            "索引编排完成：docs=%d chunks=%d vector=%d es=%d failed=%d",
            stats.documents,
            stats.chunks,
            stats.vector_points,
            stats.fulltext_written,
            stats.failed,
        )
        return stats
