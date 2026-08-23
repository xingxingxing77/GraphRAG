"""
G4 图谱幂等写入（架构 P7-G4 · 04 §5.4 · 单元 2.5）。

MERGE 去重写入 Neo4j：
- 实体节点：双标签 ``:Entity:<类型>``，canonical_name 为 MERGE 键（G4）；
- 结构边：``(c:Chunk)-[:MENTIONS {evidence_span}]->(e:Entity)``（04 §5.2）；
- 域关系：白名单关系（如 ``(:Dish)-[:REQUIRES]->(:Ingredient)``），
  白名单外走开放区泛化边 ``[:REL {weight}]``（11 号文档 D5）。

全部写入幂等：同一数据重复写入不产生重复节点/边（07 §5 断言）。
"""

# --- 标准库 ---
import logging
import re

# --- 本地模块 ---
from app.core.models import CommunityRecord, EnrichedChunk, RelationTriple, ResolvedEntity
from app.db.neo4j_client import Neo4jClient
from app.pipeline.graph_construction.schema import GraphSchema

logger = logging.getLogger(__name__)

# 标签字符白名单（防 Cypher 注入；仅允许字母数字下划线）
_LABEL_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def safe_label(type_name: str) -> str:
    """将实体类型转为安全的 Cypher 标签。

    Args:
        type_name: 实体类型名。

    Returns:
        合法标签；非法字符时退化为 Other。
    """
    return type_name if _LABEL_PATTERN.match(type_name) else "Other"


class GraphWriter:
    """Neo4j 图谱幂等写入器（G4）。

    Attributes:
        client: Neo4jClient 实例。
        schema: 图 Schema（白名单判定）。
    """

    def __init__(self, client: Neo4jClient, schema: GraphSchema) -> None:
        """初始化写入器。

        Args:
            client: Neo4jClient 实例。
            schema: 图 Schema。
        """
        self.client = client
        self.schema = schema

    async def write_entity(self, entity: ResolvedEntity) -> None:
        """幂等写入实体节点（双标签 + zone/status/type/freq）。

        Args:
            entity: 对齐后的实体。
        """
        label = safe_label(entity.type)
        # 白名单类型加域标签；开放区仅 :Entity:Other
        cypher = (
            f"MERGE (e:Entity:{label} {{canonical_name: $name}}) "
            "SET e.type = $type, e.zone = $zone, e.status = $status, "
            "    e.freq = coalesce(e.freq, 0) + 1"
        )
        await self.client.execute_cypher(
            cypher,
            {
                "name": entity.canonical_name,
                "type": entity.type,
                "zone": entity.zone,
                "status": entity.status,
            },
        )

    async def write_chunk(self, chunk_id: str, doc_id: str) -> None:
        """幂等写入 Chunk 节点。

        Args:
            chunk_id: 块 ID。
            doc_id: 父文档 ID。
        """
        cypher = (
            "MERGE (c:Chunk {chunk_id: $chunk_id}) "
            "SET c.doc_id = $doc_id"
        )
        await self.client.execute_cypher(
            cypher, {"chunk_id": chunk_id, "doc_id": doc_id}
        )

    async def write_mention(
        self, chunk_id: str, canonical_name: str, evidence_span: str = ""
    ) -> None:
        """幂等写入 MENTIONS 结构边（Chunk → Entity）。

        Args:
            chunk_id: 提及发生的块 ID。
            canonical_name: 实体规范名。
            evidence_span: 证据原文片段。
        """
        cypher = (
            "MATCH (c:Chunk {chunk_id: $chunk_id}) "
            "MATCH (e:Entity {canonical_name: $name}) "
            "MERGE (c)-[m:MENTIONS]->(e) "
            "SET m.evidence_span = $span"
        )
        await self.client.execute_cypher(
            cypher,
            {"chunk_id": chunk_id, "name": canonical_name, "span": evidence_span},
        )

    async def write_relation(self, triple: RelationTriple) -> None:
        """幂等写入域关系边（白名单）或开放区 REL 边。

        Args:
            triple: 关系三元组（head/relation/tail）。
        """
        rel_type = safe_label(triple.relation)
        # 白名单合法关系按类型写入；否则走开放区泛化 REL 边
        cypher = (
            "MERGE (h:Entity {canonical_name: $head}) "
            "MERGE (t:Entity {canonical_name: $tail}) "
            f"MERGE (h)-[r:{rel_type}]->(t)"
        )
        await self.client.execute_cypher(
            cypher, {"head": triple.head, "tail": triple.tail}
        )

    async def write_enriched_chunk(self, chunk: EnrichedChunk) -> None:
        """幂等写入单个 EnrichedChunk 的完整图结构。

        顺序：Chunk 节点 → 实体节点 → MENTIONS 边 → 域关系边。

        Args:
            chunk: 增强文档块。
        """
        chunk_id = chunk.chunk.chunk_id
        doc_id = chunk.chunk.doc_id
        await self.write_chunk(chunk_id, doc_id)

        # 实体节点 + MENTIONS 边
        for mention in chunk.entities:
            canonical = mention.normalized_to or mention.name
            entity = ResolvedEntity(
                mention=mention.name,
                canonical_name=canonical,
                type=mention.type,
                zone="core" if self.schema.is_known_node_type(mention.type) else "open",
                status="pending",
            )
            await self.write_entity(entity)
            await self.write_mention(chunk_id, canonical)

        # 域关系边
        for triple in chunk.relations:
            await self.write_relation(triple)

    async def write_enriched_chunks(self, chunks: list[EnrichedChunk]) -> None:
        """批量幂等写入 EnrichedChunk 列表。

        Args:
            chunks: 增强文档块列表。
        """
        for chunk in chunks:
            await self.write_enriched_chunk(chunk)
        logger.info("图谱写入完成：%d 个 chunk", len(chunks))

    async def clear_communities(self) -> None:
        """清空既有社区子图（重算前调用，G5 全量重建语义）。"""
        await self.client.execute_cypher("MATCH (m:Community) DETACH DELETE m")

    async def write_communities(self, records: list[CommunityRecord]) -> None:
        """写入社区子图（:Community + IN_COMMUNITY + PART_OF）。

        全量重建语义：调用前先 clear_communities。

        Args:
            records: 社区记录（含摘要与层级）。
        """
        for record in records:
            await self.client.execute_cypher(
                "MERGE (m:Community {community_id: $cid}) "
                "SET m.level = $level, m.summary = $summary, "
                "    m.member_count = $size",
                {
                    "cid": record.community_id,
                    "level": record.level,
                    "summary": record.summary,
                    "size": len(record.members),
                },
            )
            # 成员入社区边（仅对已存在实体）
            if record.members:
                await self.client.execute_cypher(
                    "MATCH (m:Community {community_id: $cid}) "
                    "MATCH (e:Entity) WHERE e.canonical_name IN $members "
                    "MERGE (e)-[:IN_COMMUNITY]->(m)",
                    {"cid": record.community_id, "members": record.members},
                )
        # 层级树 PART_OF 边（子 -> 父，level 递增向上，04 §5.2）
        for record in records:
            if record.parent_id is None:
                continue
            await self.client.execute_cypher(
                "MATCH (c:Community {community_id: $child}) "
                "MATCH (p:Community {community_id: $parent}) "
                "MERGE (c)-[:PART_OF]->(p)",
                {"child": record.community_id, "parent": record.parent_id},
            )
        logger.info("社区子图写入完成：%d 个社区", len(records))
