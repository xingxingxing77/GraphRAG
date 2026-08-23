"""G3/G4 关系抽取与图谱写入测试（单元 2.5 S3，07 §5 断言）。

断言：重复写入幂等（两次 count 不变）；MENTIONS 边 evidence 可溯源；
LLM 输出解析容错；白名单提示词包含合法关系枚举。
"""

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import (
    Chunk,
    EnrichedChunk,
    EntityMention,
    PositionMeta,
    RelationTriple,
)
from app.db.neo4j_client import Neo4jClient
from app.llm.client import ChatCompletion, LLMClient, ModelEntry
from app.pipeline.graph_construction.graph_writer import GraphWriter, safe_label
from app.pipeline.graph_construction.relation_extractor import (
    RelationExtractor,
    _build_prompt,
)
from app.pipeline.graph_construction.schema import load_graph_schema

_TEST_PREFIX = "__test_2_5__"


def _enriched_chunk() -> EnrichedChunk:
    """构造含实体与关系的测试 EnrichedChunk（实体名带测试前缀防污染）。"""
    dish = f"{_TEST_PREFIX}清蒸鲈鱼"
    ingredient = f"{_TEST_PREFIX}鲈鱼"
    chunk = Chunk(
        chunk_id=f"{_TEST_PREFIX}chunk-0",
        doc_id=f"{_TEST_PREFIX}doc",
        seq=0,
        content="清蒸鲈鱼需要鲈鱼一条。",
        title_path=["清蒸鲈鱼"],
        position=PositionMeta(start_char=0, end_char=12),
    )
    return EnrichedChunk(
        chunk=chunk,
        keywords=["鲈鱼"],
        entities=[
            EntityMention(name=dish, type="Dish", normalized_to=dish),
            EntityMention(name=ingredient, type="Ingredient", normalized_to=ingredient),
        ],
        relations=[
            RelationTriple(
                head=dish,
                relation="REQUIRES",
                tail=ingredient,
                evidence_chunk_id=chunk.chunk_id,
            )
        ],
    )


class TestSafeLabel:
    """Cypher 标签防注入。"""

    def test_valid_label_kept(self) -> None:
        assert safe_label("Dish") == "Dish"
        assert safe_label("Ingredient") == "Ingredient"

    def test_invalid_label_falls_back(self) -> None:
        assert safe_label("Drop (x)") == "Other"
        assert safe_label("`) DETACH DELETE") == "Other"


class TestRelationExtractorParsing:
    """G3 输出解析（stub LLM，07 §3）。"""

    def _extractor(self) -> RelationExtractor:
        entry = ModelEntry(base_url="http://stub/v1", api_key_ref="K", model="stub")
        client = LLMClient(entry=entry, api_key="stub")
        return RelationExtractor(load_graph_schema(), client)

    def test_parse_valid_triples(self) -> None:
        extractor = self._extractor()
        content = (
            '[{"head": "清蒸鲈鱼", "relation": "REQUIRES", "tail": "鲈鱼",'
            ' "evidence": "需要鲈鱼一条"}]'
        )
        triples = extractor._parse_triples(content, "chunk-x")
        assert len(triples) == 1
        assert triples[0].head == "清蒸鲈鱼"
        assert triples[0].relation == "REQUIRES"
        assert triples[0].tail == "鲈鱼"
        assert triples[0].evidence_chunk_id == "chunk-x"

    def test_parse_with_surrounding_text(self) -> None:
        extractor = self._extractor()
        content = '抽取结果如下：[{"head": "A", "relation": "REL", "tail": "B"}] 完毕。'
        triples = extractor._parse_triples(content, "c")
        assert len(triples) == 1

    def test_parse_empty_array(self) -> None:
        extractor = self._extractor()
        assert extractor._parse_triples("[]", "c") == []

    def test_parse_invalid_json_returns_empty(self) -> None:
        extractor = self._extractor()
        assert extractor._parse_triples("无法解析的内容", "c") == []
        assert extractor._parse_triples("{broken json}", "c") == []

    def test_parse_skips_incomplete_items(self) -> None:
        extractor = self._extractor()
        content = '[{"head": "A", "relation": "REL"}, {"head": "", "relation": "REL", "tail": "B"}]'
        assert extractor._parse_triples(content, "c") == []

    def test_prompt_contains_whitelist_edges(self) -> None:
        prompt = _build_prompt("任意文本", load_graph_schema())
        assert "REQUIRES" in prompt
        assert "HAS_STEP" in prompt
        assert "REL" in prompt  # 开放区标记规则

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LLM 调用失败降级为空列表，不阻断管道。"""
        extractor = self._extractor()

        async def failing_chat(*args: object, **kwargs: object) -> ChatCompletion:
            raise RuntimeError("stub LLM down")

        monkeypatch.setattr(extractor.llm_client, "chat", failing_chat)
        assert await extractor.extract("任意文本", "chunk-x") == []


class TestGraphWriterNeo4j:
    """G4 幂等写入（集成，Neo4j 不可达时跳过）。"""

    @pytest.mark.asyncio
    async def test_idempotent_write_and_mentions(self) -> None:
        client = Neo4jClient("bolt://localhost:7687", "neo4j", "password")
        if not await client.check_health():
            pytest.skip("Neo4j 不可达，集成用例跳过")
        schema = load_graph_schema()
        writer = GraphWriter(client, schema)
        chunk = _enriched_chunk()
        try:
            # 清理测试数据
            await client.execute_cypher(
                "MATCH (n) WHERE n.canonical_name STARTS WITH $p "
                "OR n.chunk_id STARTS WITH $p DETACH DELETE n",
                {"p": _TEST_PREFIX},
            )

            await writer.write_enriched_chunk(chunk)
            dish = f"{_TEST_PREFIX}清蒸鲈鱼"
            ingredient = f"{_TEST_PREFIX}鲈鱼"
            after_first = await client.execute_cypher(
                "MATCH (e:Entity) WHERE e.canonical_name IN $names "
                "RETURN count(e) AS c",
                {"names": [dish, ingredient]},
            )
            # 双写幂等：重复写入节点/边数量不变（07 §5）
            await writer.write_enriched_chunk(chunk)
            after_second = await client.execute_cypher(
                "MATCH (e:Entity) WHERE e.canonical_name IN $names "
                "RETURN count(e) AS c",
                {"names": [dish, ingredient]},
            )
            assert after_first[0]["c"] == 2
            assert after_second[0]["c"] == after_first[0]["c"]

            # MENTIONS 边幂等 + 溯源
            mentions = await client.execute_cypher(
                "MATCH (c:Chunk {chunk_id: $cid})-[m:MENTIONS]->(e:Entity) "
                "RETURN count(m) AS c, collect(e.canonical_name) AS names",
                {"cid": chunk.chunk.chunk_id},
            )
            assert mentions[0]["c"] == 2
            assert set(mentions[0]["names"]) == {dish, ingredient}

            # 域关系边幂等
            rels = await client.execute_cypher(
                "MATCH (h:Entity {canonical_name: $dish})"
                "-[r:REQUIRES]->(t:Entity {canonical_name: $ingredient}) "
                "RETURN count(r) AS c",
                {"dish": dish, "ingredient": ingredient},
            )
            assert rels[0]["c"] == 1

            # 双标签与 zone 标记
            node = await client.execute_cypher(
                "MATCH (e:Entity:Dish {canonical_name: $dish}) "
                "RETURN e.zone AS zone, e.status AS status",
                {"dish": dish},
            )
            assert node[0]["zone"] == "core"
        finally:
            await client.execute_cypher(
                "MATCH (n) WHERE n.canonical_name STARTS WITH $p "
                "OR n.chunk_id STARTS WITH $p DETACH DELETE n",
                {"p": _TEST_PREFIX},
            )
            await client.close()
