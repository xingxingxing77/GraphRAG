"""
Elasticsearch 客户端封装（04 §6 · J5/J6 · 单元 3.2）。

双索引（rag_entities / rag_chunks）+ IK 分析器（idx_ik_max 建索引 /
qry_ik_smart 查询）+ 别名版本化（rag_{name}_v{n} → 别名 rag_{name}，
零停机重建：建 v(n+1) → 灌数 → 校验 count → 原子切别名 → 删旧）。
`_id` 裸值 = entity_id / chunk_id（与 Neo4j/Qdrant 三方一致，11 D9）。
"""

# --- 标准库 ---
import logging
from typing import Any, Optional

# --- 第三方库 ---
from elasticsearch import AsyncElasticsearch
from elasticsearch import NotFoundError as EsNotFoundError

logger = logging.getLogger(__name__)

# 索引别名与版本化命名（04 §6.4）
ENTITIES_ALIAS = "rag_entities"
CHUNKS_ALIAS = "rag_chunks"

# 共用分析器定义（04 §6.1）
_IK_SETTINGS: dict[str, Any] = {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
        "analyzer": {
            "idx_ik_max": {"type": "custom", "tokenizer": "ik_max_word"},
            "qry_ik_smart": {"type": "custom", "tokenizer": "ik_smart"},
        }
    },
}

# rag_entities mapping（04 §6.2）
_ENTITIES_MAPPINGS: dict[str, Any] = {
    "properties": {
        "entity_id": {"type": "keyword"},
        "canonical_name": {"type": "keyword"},
        "name": {"type": "text", "analyzer": "idx_ik_max", "search_analyzer": "qry_ik_smart"},
        "aliases": {"type": "text", "analyzer": "idx_ik_max", "search_analyzer": "qry_ik_smart"},
        "description": {"type": "text", "analyzer": "idx_ik_max", "search_analyzer": "qry_ik_smart"},
        "type": {"type": "keyword"},
        "zone": {"type": "keyword"},
    }
}

# rag_chunks mapping（04 §6.3）
_CHUNKS_MAPPINGS: dict[str, Any] = {
    "properties": {
        "chunk_id": {"type": "keyword"},
        "doc_id": {"type": "keyword"},
        "content": {"type": "text", "analyzer": "idx_ik_max", "search_analyzer": "qry_ik_smart"},
        "title_path": {"type": "text", "analyzer": "idx_ik_max", "search_analyzer": "qry_ik_smart"},
        "created_at": {"type": "date"},
    }
}


class ESClient:
    """Elasticsearch 异步客户端封装。

    Attributes:
        host: ES 服务地址（含端口）。
    """

    def __init__(self, host: str) -> None:
        """初始化 ES 客户端。

        Args:
            host: ES 服务地址，如 http://localhost:9200。
        """
        self.host = host
        self._client: Optional[AsyncElasticsearch] = None

    async def connect(self) -> None:
        """建立 ES 异步客户端连接。"""
        if self._client is None:
            self._client = AsyncElasticsearch(hosts=[self.host])

    async def close(self) -> None:
        """关闭 ES 客户端连接。"""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def _ensure_client(self) -> AsyncElasticsearch:
        """确保客户端已连接。

        Returns:
            AsyncElasticsearch 实例。
        """
        if self._client is None:
            await self.connect()
        assert self._client is not None
        return self._client

    async def ensure_indices(self) -> None:
        """确保双索引与别名就绪（幂等）。

        创建 rag_entities_v1 / rag_chunks_v1 并绑定别名；
        别名已存在时跳过。

        Raises:
            Exception: IK 插件未安装等索引创建失败。
        """
        client = await self._ensure_client()
        for alias, mappings in (
            (ENTITIES_ALIAS, _ENTITIES_MAPPINGS),
            (CHUNKS_ALIAS, _CHUNKS_MAPPINGS),
        ):
            if await client.indices.exists_alias(name=alias):
                continue
            index = f"{alias}_v1"
            if not await client.indices.exists(index=index):
                await client.indices.create(
                    index=index, settings=_IK_SETTINGS, mappings=mappings
                )
            await client.indices.put_alias(index=index, name=alias)

    async def index_doc(self, alias: str, doc_id: str, document: dict[str, Any]) -> None:
        """按 _id 写入/覆盖单条文档（_id 裸值 = entity_id/chunk_id）。

        Args:
            alias: 索引别名（rag_entities / rag_chunks）。
            doc_id: 文档 _id。
            document: 文档内容。
        """
        client = await self._ensure_client()
        await client.index(index=alias, id=doc_id, document=document)

    async def bulk_index(
        self, alias: str, docs: list[tuple[str, dict[str, Any]]]
    ) -> int:
        """批量写入文档。

        Args:
            alias: 索引别名。
            docs: [(_id, document), ...] 列表。

        Returns:
            写入条数。
        """
        if not docs:
            return 0
        client = await self._ensure_client()
        operations: list[dict[str, Any]] = []
        for doc_id, document in docs:
            operations.append({"index": {"_index": alias, "_id": doc_id}})
            operations.append(document)
        await client.bulk(operations=operations, refresh=False)
        return len(docs)

    async def delete_by_doc(self, alias: str, doc_id: str) -> int:
        """按 doc_id 删除（04 §7.2 ES 侧 delete_by_query）。

        Args:
            alias: 索引别名。
            doc_id: 文档 ID。

        Returns:
            删除条数。
        """
        client = await self._ensure_client()
        resp = await client.delete_by_query(
            index=alias,
            query={"term": {"doc_id": doc_id}},
            ignore_unavailable=True,
        )
        return int(resp.get("deleted", 0))

    async def delete_by_id(self, alias: str, doc_id: str) -> None:
        """按 _id 删除单条（不存在时忽略）。

        Args:
            alias: 索引别名。
            doc_id: 文档 _id。
        """
        client = await self._ensure_client()
        try:
            await client.delete(index=alias, id=doc_id)
        except EsNotFoundError:
            pass

    async def search(
        self,
        alias: str,
        field: str,
        text: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """IK 全文检索（qry_ik_smart 查询分析器）。

        Args:
            alias: 索引别名。
            field: 检索字段（name / content 等）。
            text: 查询文本。
            top_k: 返回条数。

        Returns:
            命中列表，每项 {id, score, source}。
        """
        client = await self._ensure_client()
        resp = await client.search(
            index=alias,
            query={"match": {field: {"query": text, "analyzer": "qry_ik_smart"}}},
            size=top_k,
        )
        hits = resp.get("hits", {}).get("hits", [])
        return [
            {"id": h["_id"], "score": float(h.get("_score") or 0.0), "source": h.get("_source") or {}}
            for h in hits
        ]

    async def analyze(self, alias: str, text: str, analyzer: str = "ik_smart") -> list[str]:
        """IK 分词调试（_analyze API，02 §3.11 debug/analyze）。

        Args:
            alias: 索引别名（提供分析器上下文）。
            text: 待分词文本。
            analyzer: 分析器名（ik_smart / ik_max_word / idx_ik_max 等）。

        Returns:
            分词 token 列表。
        """
        client = await self._ensure_client()
        resp = await client.indices.analyze(index=alias, analyzer=analyzer, text=text)
        return [str(t["token"]) for t in resp.get("tokens", [])]

    async def count(self, alias: str) -> int:
        """统计索引文档数。

        Args:
            alias: 索引别名。

        Returns:
            文档数。
        """
        client = await self._ensure_client()
        resp = await client.count(index=alias, ignore_unavailable=True)
        return int(resp.get("count", 0))

    async def alias_target(self, alias: str) -> str | None:
        """查询别名当前指向的索引名。

        Args:
            alias: 别名。

        Returns:
            索引名；别名不存在返回 None。
        """
        client = await self._ensure_client()
        try:
            resp = await client.indices.get_alias(name=alias)
        except EsNotFoundError:
            return None
        names = list(resp.keys())
        return names[0] if names else None

    async def alias_atomic_swap(self, alias: str, new_index: str) -> str | None:
        """别名原子切换（04 §6.4 零停机重建）。

        将别名从旧索引原子切到 new_index 并删除旧索引。

        Args:
            alias: 别名。
            new_index: 新索引名。

        Returns:
            被删除的旧索引名；无旧索引时返回 None。
        """
        client = await self._ensure_client()
        old_index = await self.alias_target(alias)
        actions: list[dict[str, Any]] = [{"add": {"index": new_index, "alias": alias}}]
        if old_index is not None:
            actions.insert(0, {"remove": {"index": old_index, "alias": alias}})
        await client.indices.update_aliases(actions=actions)
        if old_index is not None and old_index != new_index:
            await client.indices.delete(index=old_index, ignore_unavailable=True)
        return old_index

    async def check_health(self) -> bool:
        """检查 ES 连接健康状态。

        Returns:
            True 表示连接正常。
        """
        try:
            client = await self._ensure_client()
            await client.ping()
            return True
        except Exception:  # noqa: BLE001 - 健康检查不抛错
            return False

    async def ik_available(self) -> bool:
        """检测 IK 分析器插件是否可用。

        Returns:
            True 表示 IK 就绪。
        """
        try:
            await self.analyze(ENTITIES_ALIAS, "测试", analyzer="ik_smart")
            return True
        except Exception:  # noqa: BLE001 - 插件缺失或索引未建
            return False
