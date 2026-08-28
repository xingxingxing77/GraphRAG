"""
Qdrant 向量数据库客户端封装（04 §3 · 单元 3.1）。

封装 AsyncQdrantClient 的连接管理、Collection 管理与向量操作：
- 业务集合 rag_{doc_type}：named vectors（dense 1024 Cosine + sparse Dot），
  hnsw m=16 / ef_construct=200（04 §3.1）；
- Point ID 由 chunk_id 确定性派生（uuid5），payload 携带 chunk_id，
  保证幂等与 Neo4j/ES 三方映射（04 §3.1 Point ID 规范）；
- batch upsert（batch_size=100，架构 P6）。
"""

# --- 标准库 ---
import uuid
from typing import Any, Optional

# --- 第三方库 ---
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    HnswConfigDiff,
    MatchValue,
    PointIdsList,
    PointStruct,
    Range,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

# Point ID 派生命名空间（chunk_id → 确定性 UUID）
_POINT_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "graphrag://qdrant-point")

# 稀疏向量 named vector 名称（04 §3.1）
SPARSE_VECTOR_NAME = "sparse"
DENSE_VECTOR_NAME = "dense"


def point_id_from_chunk_id(chunk_id: str) -> str:
    """由 chunk_id 派生确定性 Point ID（uuid5，幂等）。

    Args:
        chunk_id: 块 ID（{doc_id}-{seq}）。

    Returns:
        UUID 字符串（同 chunk_id 恒同值）。
    """
    return str(uuid.uuid5(_POINT_ID_NAMESPACE, chunk_id))


class QdrantDBClient:
    """Qdrant 异步客户端封装。

    Attributes:
        host: Qdrant 服务地址。
        port: Qdrant HTTP 端口（6333）。
    """

    def __init__(self, host: str, port: int) -> None:
        """初始化 Qdrant 客户端。

        Args:
            host: Qdrant 服务地址。
            port: Qdrant HTTP 端口。
        """
        self.host = host
        self.port = port
        self._client: Optional[AsyncQdrantClient] = None

    async def connect(self) -> None:
        """建立 Qdrant 异步客户端连接。"""
        if self._client is None:
            self._client = AsyncQdrantClient(
                host=self.host, port=self.port, check_compatibility=False
            )

    async def close(self) -> None:
        """关闭 Qdrant 客户端连接。"""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def _ensure_client(self) -> AsyncQdrantClient:
        """确保客户端已连接。

        Returns:
            AsyncQdrantClient 实例。
        """
        if self._client is None:
            await self.connect()
        assert self._client is not None
        return self._client

    async def ensure_collection(
        self,
        collection_name: str,
        dense_vector_size: int = 1024,
        distance: Distance = Distance.COSINE,
    ) -> None:
        """创建业务 Collection（幂等，已存在则跳过）。

        规格按 04 §3.1：dense 1024 Cosine + named sparse（Dot）+
        hnsw m=16 / ef_construct=200。

        Args:
            collection_name: Collection 名称（rag_{doc_type}）。
            dense_vector_size: 密集向量维度（BGE-M3 = 1024）。
            distance: 密集向量距离度量。
        """
        client = await self._ensure_client()
        if await client.collection_exists(collection_name):
            # 自愈：rag_cache 等依赖 payload 索引的集合，确保关键字段索引存在
            # （缺失会导致 Range 过滤恒 miss / 失效联动不生效，变相 no-cache）
            if collection_name in ("rag_cache", "rag_episodic"):
                try:
                    await self._ensure_memory_payload_indexes(collection_name)
                except Exception as exc:  # noqa: BLE001
                    import logging as _log

                    _log.getLogger(__name__).warning("ensure_payload_index 自愈失败 %s: %s", collection_name, exc)
            return
        await client.create_collection(
            collection_name=collection_name,
            vectors_config={
                DENSE_VECTOR_NAME: VectorParams(size=dense_vector_size, distance=distance)
            },
            sparse_vectors_config={SPARSE_VECTOR_NAME: SparseVectorParams()},
            hnsw_config=HnswConfigDiff(m=16, ef_construct=200),
        )
        # 新建后立即建 payload 索引（避免首批写入后过滤不生效）
        if collection_name in ("rag_cache", "rag_episodic"):
            try:
                await self._ensure_memory_payload_indexes(collection_name)
            except Exception as exc:  # noqa: BLE001
                import logging as _log

                _log.getLogger(__name__).warning("ensure_payload_index 自愈失败 %s: %s", collection_name, exc)

    async def _ensure_memory_payload_indexes(self, collection_name: str) -> None:
        """按集合口径建立 payload 索引（m3：与实际 payload 字段对齐）。

        - rag_cache：created_at（TTL Range 过滤）+ matched_doc_ids（失效
          联动反查）+ embedding_model（M6 模型隔离过滤）；
        - rag_episodic：timestamp（purge_expired Range 依据——payload 写的
          是 timestamp 而非 created_at，原索引字段错位形同全表扫描）+
          user_id/session_id（隔离与排除过滤，keyword）。

        Args:
            collection_name: 集合名。
        """
        if collection_name == "rag_cache":
            await self.ensure_payload_index(collection_name, "created_at")
            await self.ensure_payload_index(collection_name, "matched_doc_ids")
            await self.ensure_payload_index(collection_name, "embedding_model")
        else:
            await self.ensure_payload_index(collection_name, "timestamp")
            await self.ensure_payload_index(collection_name, "user_id")
            await self.ensure_payload_index(collection_name, "session_id")

    async def upsert_points(
        self,
        collection_name: str,
        points: list[PointStruct],
        batch_size: int = 100,
    ) -> None:
        """批量写入向量点（幂等：同 point id 覆盖写）。

        Args:
            collection_name: Collection 名称。
            points: 要写入的点列表。
            batch_size: 批量写入大小（架构 P6 = 100）。
        """
        client = await self._ensure_client()
        for i in range(0, len(points), batch_size):
            await client.upsert(
                collection_name=collection_name,
                points=points[i : i + batch_size],
            )

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int = 10,
        filter_condition: Optional[Filter] = None,
    ) -> list[dict[str, Any]]:
        """密集向量相似度检索（named vector "dense"）。

        Args:
            collection_name: Collection 名称。
            query_vector: 查询向量。
            top_k: 返回数量。
            filter_condition: 过滤条件（可选）。

        Returns:
            检索结果列表，每项 {id, chunk_id, score, payload}；
            score 为 Cosine 相似度原始分。
        """
        client = await self._ensure_client()
        result = await client.query_points(
            collection_name=collection_name,
            query=query_vector,
            using=DENSE_VECTOR_NAME,
            limit=top_k,
            query_filter=filter_condition,
            with_payload=True,
        )
        return self._format_hits(result.points)

    async def search_sparse(
        self,
        collection_name: str,
        sparse_vector: dict[int, float],
        top_k: int = 10,
        filter_condition: Optional[Filter] = None,
    ) -> list[dict[str, Any]]:
        """稀疏向量检索（named vector "sparse"，Dot Product 口径）。

        Args:
            collection_name: Collection 名称。
            sparse_vector: 稀疏向量 {token_id: weight}。
            top_k: 返回数量。
            filter_condition: 过滤条件（可选）。

        Returns:
            检索结果列表，格式同 search。空向量返回空列表（P1 防 400）。
        """
        if not sparse_vector:
            return []
        client = await self._ensure_client()
        indices = sorted(sparse_vector.keys())
        values = [sparse_vector[i] for i in indices]
        result = await client.query_points(
            collection_name=collection_name,
            query=SparseVector(indices=indices, values=values),
            using=SPARSE_VECTOR_NAME,
            limit=top_k,
            query_filter=filter_condition,
            with_payload=True,
        )
        return self._format_hits(result.points)

    async def scroll_by_doc(
        self,
        collection_name: str,
        doc_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """按 doc_id 过滤滚动查询（payload 匹配，04 §7.2 删除联动同源）。

        Args:
            collection_name: Collection 名称。
            doc_id: 文档 ID。
            limit: 返回上限。

        Returns:
            点列表，每项 {id, chunk_id, score: None, payload}。
        """
        client = await self._ensure_client()
        flt = Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
        )
        records, _ = await client.scroll(
            collection_name=collection_name,
            scroll_filter=flt,
            limit=limit,
            with_payload=True,
        )
        return [
            {
                "id": str(r.id),
                "chunk_id": str((r.payload or {}).get("chunk_id", "")),
                "score": None,
                "payload": r.payload or {},
            }
            for r in records
        ]

    async def delete_by_doc(self, collection_name: str, doc_id: str) -> None:
        """按 doc_id 删除点（04 §7.2 文档删除联动）。

        Args:
            collection_name: Collection 名称。
            doc_id: 文档 ID。
        """
        await self.delete_by_payload_match(collection_name, "doc_id", doc_id)

    async def clear_collection(self, collection_name: str) -> int:
        """清空集合全部点（全量重建前置，BUG-E）。

        Args:
            collection_name: Collection 名称。

        Returns:
            实际删除的点数（集合不存在时返回 0）。
        """
        client = await self._ensure_client()
        if not await client.collection_exists(collection_name):
            return 0
        deleted = 0
        offset: Any = None
        while True:
            records, offset = await client.scroll(
                collection_name=collection_name,
                limit=500,
                with_payload=False,
            )
            if not records:
                break
            ids = [r.id for r in records]
            await client.delete(
                collection_name=collection_name,
                points_selector=PointIdsList(points=ids),
            )
            deleted += len(ids)
            if offset is None:
                break
        return deleted

    async def delete_by_payload_match(
        self,
        collection_name: str,
        key: str,
        value: Any,
    ) -> int:
        """按 payload 字段精确匹配删除（数组字段为包含语义）。

        记忆层使用：rag_cache 按 matched_doc_ids 反查失效（04 §7）、
        rag_episodic 按 session_id 级联删除（07 A-05）。

        Args:
            collection_name: Collection 名称。
            key: payload 字段名。
            value: 匹配值（payload 为数组时命中含该值的点）。

        Returns:
            实际删除的点数（集合不存在时返回 0；admin cache/clear
            purged 计数来源，02 §3.10）。
        """
        client = await self._ensure_client()
        if not await client.collection_exists(collection_name):
            return 0
        flt = Filter(must=[FieldCondition(key=key, match=MatchValue(value=value))])
        deleted = 0
        offset: Any = None
        while True:
            records, offset = await client.scroll(
                collection_name=collection_name,
                scroll_filter=flt,
                limit=500,
                with_payload=False,
            )
            if not records:
                break
            ids = [r.id for r in records]
            await client.delete(
                collection_name=collection_name,
                points_selector=PointIdsList(points=ids),
            )
            deleted += len(ids)
            if offset is None:
                break
        return deleted

    async def delete_created_before(
        self,
        collection_name: str,
        field: str,
        before_unix: int,
        batch: int = 500,
    ) -> int:
        """删除数值字段早于阈值的点（rag_cache 应用层 TTL 清理，04 §3.3）。

        Qdrant 无原生 TTL，过期策略为应用层定时任务。

        Args:
            collection_name: Collection 名称。
            field: 时间戳 payload 字段名（unix 秒）。
            before_unix: 删除该时刻之前的点。
            batch: 单轮滚动拉取上限。

        Returns:
            实际删除的点数。
        """
        client = await self._ensure_client()
        if not await client.collection_exists(collection_name):
            return 0
        flt = Filter(
            must=[FieldCondition(key=field, range=Range(lt=float(before_unix)))]
        )
        deleted = 0
        while True:
            records, offset = await client.scroll(
                collection_name=collection_name,
                scroll_filter=flt,
                limit=batch,
                with_payload=False,
            )
            if not records:
                break
            ids = [r.id for r in records]
            await client.delete(
                collection_name=collection_name,
                points_selector=PointIdsList(points=ids),
            )
            deleted += len(ids)
            if offset is None:
                break
        return deleted

    async def count(self, collection_name: str, doc_id: str | None = None) -> int:
        """统计 Collection 点数（可按 doc_id 过滤）。

        Args:
            collection_name: Collection 名称。
            doc_id: 可选文档 ID 过滤。

        Returns:
            点数量。
        """
        client = await self._ensure_client()
        flt = None
        if doc_id is not None:
            flt = Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            )
        result = await client.count(
            collection_name=collection_name, count_filter=flt, exact=True
        )
        return int(result.count)

    async def list_collections(self) -> list[str]:
        """列出全部 Collection 名称。

        Returns:
            Collection 名称列表。
        """
        client = await self._ensure_client()
        result = await client.get_collections()
        return [c.name for c in result.collections]

    async def ensure_payload_index(self, collection_name: str, field_name: str) -> None:
        """幂等创建 payload 索引（Range/Keyword，按字段自动推断）。

        rag_cache 的 created_at（integer）与 matched_doc_ids（keyword 数组）
        需建索引后 Range/匹配过滤才高效且可靠；缺失时变相恒 miss 触发 no-cache。
        m3：rag_episodic 的 timestamp 同为 integer Range 依据，一并纳入推断。

        Args:
            collection_name: 集合名。
            field_name: payload 字段名。
        """
        client = await self._ensure_client()
        # 已存在则跳过（用 get_collection 探查 payload_schema）
        try:
            info = await client.get_collection(collection_name)
            schema = getattr(info.config.params, "payload_schema", None) or getattr(
                info, "payload_schema", None
            )
            if schema and field_name in schema:
                return
        except Exception:
            pass
        # 按字段类型选择索引（时间戳字段 integer 走 Range，其余 keyword）
        field_type = (
            "integer" if field_name in ("created_at", "timestamp") else "keyword"
        )
        try:
            await client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_type,  # type: ignore[arg-type]
            )
        except Exception as exc:
            # 已存在或并发创建竞争，记录后忽略（P1 M-04）
            import logging as _log

            _log.getLogger(__name__).debug("ensure_payload_index 忽略异常 %s/%s: %s", collection_name, field_name, exc)
            return

    async def check_health(self) -> bool:
        """检查 Qdrant 连接健康状态。

        Returns:
            True 表示连接正常。
        """
        try:
            await self.list_collections()
            return True
        except Exception:  # noqa: BLE001 - 健康检查不抛错
            return False

    @staticmethod
    def _format_hits(points: list[Any]) -> list[dict[str, Any]]:
        """格式化检索命中为统一字典结构。

        Args:
            points: query_points 返回的点列表。

        Returns:
            [{id, chunk_id, score, payload}, ...]。
        """
        return [
            {
                "id": str(p.id),
                "chunk_id": str((p.payload or {}).get("chunk_id", "")),
                "score": float(p.score),
                "payload": p.payload or {},
            }
            for p in points
        ]
