"""
全文索引构建器（ES 版，架构 J5/J6 · 11 D9 · 单元 3.2）。

全文检索外置 Elasticsearch（J5：Neo4j 不自建全文索引）：
- 图谱/管道写入成功后由 es_syncer 异步同步 ES（rag_entities / rag_chunks）；
- `_id` 裸值 = entity_id / chunk_id（与 Neo4j/Qdrant 三方一致）；
- 同步失败入 Redis List 死信队列，admin 可重放（11 D9）。
"""

# --- 标准库 ---
import json
import logging
from typing import Any

# --- 本地模块 ---
from app.db.es_client import CHUNKS_ALIAS, ENTITIES_ALIAS, ESClient
from app.db.redis_client import RedisClient

logger = logging.getLogger(__name__)


class ESSyncer:
    """ES 同步器（es_syncer，J6 写入侧）。

    Attributes:
        es: ES 客户端。
        redis: Redis 客户端（死信队列）。
    """

    def __init__(self, es: ESClient, redis: RedisClient) -> None:
        """初始化 ES 同步器。

        Args:
            es: ES 客户端。
            redis: Redis 客户端（死信队列载体）。
        """
        self.es = es
        self.redis = redis

    async def sync_entities(self, entities: list[dict[str, Any]]) -> int:
        """批量同步实体文档到 rag_entities（_id = entity_id）。

        Args:
            entities: 实体文档列表，每项须含 entity_id 字段
                （canonical_name/name/aliases/description/type/zone）。

        Returns:
            成功写入条数（失败批次入死信，计 0）。
        """
        docs = [
            (str(e["entity_id"]), {k: v for k, v in e.items()})
            for e in entities
            if e.get("entity_id")
        ]
        return await self._sync_batch(ENTITIES_ALIAS, docs)

    async def sync_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """批量同步 chunk 文档到 rag_chunks（_id = chunk_id）。

        Args:
            chunks: chunk 文档列表，每项须含 chunk_id 字段
                （doc_id/content/title_path/created_at）。

        Returns:
            成功写入条数（失败批次入死信，计 0）。
        """
        docs = [
            (str(c["chunk_id"]), {k: v for k, v in c.items()})
            for c in chunks
            if c.get("chunk_id")
        ]
        return await self._sync_batch(CHUNKS_ALIAS, docs)

    async def replay_dead_letter(self, max_items: int = 100) -> int:
        """重放死信队列（admin 触发，FIFO 消费）。

        Args:
            max_items: 单次重放上限。

        Returns:
            成功重放的批次数；仍失败的批次重新入队。
        """
        replayed = 0
        for _ in range(max_items):
            message = await self.redis.dead_letter_pop()
            if message is None:
                break
            try:
                payload = json.loads(message)
                alias = str(payload["alias"])
                docs = [(str(_id), doc) for _id, doc in payload["docs"]]
                await self.es.bulk_index(alias, docs)
                replayed += 1
            except Exception as exc:  # noqa: BLE001 - 重放失败回队
                logger.warning("死信重放失败，重新入队: %s", exc)
                await self.redis.dead_letter_push(message)
                break
        return replayed

    async def _sync_batch(self, alias: str, docs: list[tuple[str, dict[str, Any]]]) -> int:
        """批量同步（失败整批入死信）。

        Args:
            alias: 索引别名。
            docs: [(_id, doc), ...]。

        Returns:
            成功写入条数。
        """
        if not docs:
            return 0
        try:
            await self.es.ensure_indices()
            return await self.es.bulk_index(alias, docs)
        except Exception as exc:  # noqa: BLE001 - 同步失败入死信不阻断管道
            logger.warning("ES 同步失败，批次入死信队列: %s", exc)
            message = json.dumps(
                {"alias": alias, "docs": docs}, ensure_ascii=False
            )
            try:
                await self.redis.dead_letter_push(message)
            except Exception:  # noqa: BLE001 - Redis 也不可用时仅告警
                logger.error("死信入队失败（Redis 不可用），批次丢失: %s", exc)
            return 0
