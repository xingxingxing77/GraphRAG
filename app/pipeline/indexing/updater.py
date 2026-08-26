"""
索引更新策略（GAP-A3 · 编排入口）。

协调 PipelineService（端到端索引编排）与三存储的删除能力：
- full_rebuild：对给定文档全量重跑 P2-P6 管线并三索引幂等写入。
- incremental_update：对变更文档重跑管线（索引幂等 upsert）。
- delete_document：从 Qdrant / Neo4j / ES 三处删除 doc_id 相关条目。

注意（GAP-B1）：全量「清空重建」语义与 admin index/rebuild 的
「校验修复」档是两个不同入口——本类仅提供「重嵌入 upsert」语义，
「先清空再重建」由调用方（admin rebuild full 档）在调用前自行清空，
以避免 J18 禁热更的全量重建误触发。
"""

# --- 标准库 ---
import logging

# --- 本地模块 ---
from app.core.models import RawDocument
from app.db.es_client import CHUNKS_ALIAS
from app.pipeline.indexing.pipeline_service import IndexStats, PipelineService

logger = logging.getLogger(__name__)

# 业务集合前缀（04 §3.1 rag_{doc_type}）
_COLLECTION_PREFIX = "rag_"


class IndexUpdater:
    """索引更新策略（编排入口，GAP-A3）。

    Attributes:
        pipeline: 端到端索引编排器。
    """

    def __init__(self, pipeline: PipelineService) -> None:
        """初始化 IndexUpdater。

        Args:
            pipeline: PipelineService 实例（含三 indexer 与 P2-P5 管线）。
        """
        self.pipeline = pipeline

    async def full_rebuild(self, documents: list[RawDocument]) -> IndexStats:
        """全量重建：对全部文档重跑管线并幂等写入三索引。

        幂等性由各 indexer 保证（point id / MERGE / _id 确定性派生），
        重复调用不产生重复数据。

        Args:
            documents: RawDocument 列表（采集层输出）。

        Returns:
            IndexStats: 重建统计。
        """
        logger.info("全量重建开始：%d 个文档", len(documents))
        return await self.pipeline.index_documents(documents)

    async def incremental_update(self, documents: list[RawDocument]) -> IndexStats:
        """增量更新：对变更文档重跑管线（幂等 upsert 覆盖旧值）。

        Args:
            documents: 变更的 RawDocument 列表。

        Returns:
            IndexStats: 本次更新统计。
        """
        logger.info("增量更新开始：%d 个文档", len(documents))
        return await self.pipeline.index_documents(documents)

    async def delete_document(self, doc_id: str) -> None:
        """删除指定文档在 Qdrant / Neo4j / ES 的全部索引数据。

        幂等：doc_id 不存在时各存储删除为空操作不报错。

        Args:
            doc_id: 文档唯一标识（RawDocument.doc_id）。
        """
        # ① Qdrant：遍历业务集合按 doc_id 删 points
        try:
            collections = await self.pipeline.vector_indexer.db_client.list_collections()
            for name in collections:
                if name.startswith(_COLLECTION_PREFIX):
                    await self.pipeline.vector_indexer.db_client.delete_by_doc(name, doc_id)
        except Exception as exc:  # noqa: BLE001 - 删除失败记日志继续（M3/D5）
            logger.warning("Qdrant 删除 doc_id=%s 失败: %s", doc_id, exc)

        # ② Neo4j：删除 Chunk/Document 节点（级联 MENTIONS/REL 边自动清）
        for cypher in (
            "MATCH (c:Chunk {doc_id: $doc_id}) DETACH DELETE c",
            "MATCH (d:Document {doc_id: $doc_id}) DETACH DELETE d",
        ):
            try:
                await self.pipeline.graph_writer.client.execute_cypher(
                    cypher, {"doc_id": doc_id}
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Neo4j 删除 doc_id=%s 失败: %s", doc_id, exc)

        # ③ ES：按 doc_id 删 chunk 文档（实体随社区重算/重建同步，J6）
        try:
            await self.pipeline.es_syncer.es.delete_by_doc(CHUNKS_ALIAS, doc_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ES 删除 doc_id=%s 失败: %s", doc_id, exc)
        logger.info("删除 doc_id=%s 完成", doc_id)
