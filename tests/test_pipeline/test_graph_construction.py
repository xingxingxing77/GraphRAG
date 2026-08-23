"""P7 图谱构建测试（单元 2.4 S3，07 §5 断言）。

断言：别名归并用例；[0.80,0.92) 灰区入审核队列；白名单/开放区
zone 标记正确；唯一约束创建成功（04 §5.3，Neo4j 集成）。
"""

# --- 标准库 ---
import math

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import EntityMention, EmbeddingResult
from app.db.neo4j_client import Neo4jClient
from app.pipeline.graph_construction.entity_resolver import (
    AliasTable,
    EntityResolver,
    cosine_similarity,
    load_alias_table,
    normalize_name,
)
from app.pipeline.graph_construction.schema import load_graph_schema


class TestGraphSchema:
    """G1 Schema 加载与白名单校验。"""

    def test_load_node_and_edge_types(self) -> None:
        schema = load_graph_schema()
        assert set(schema.node_types) == {"Dish", "Ingredient", "Step", "Technique"}
        assert schema.alignment.vector_merge_threshold == 0.92
        assert schema.alignment.review_low == 0.80
        assert schema.alignment.review_high == 0.92

    def test_is_known_node_type(self) -> None:
        schema = load_graph_schema()
        assert schema.is_known_node_type("Dish") is True
        assert schema.is_known_node_type("Ingredient") is True
        assert schema.is_known_node_type("Restaurant") is False

    def test_is_allowed_edge(self) -> None:
        schema = load_graph_schema()
        assert schema.is_allowed_edge("Dish", "REQUIRES", "Ingredient") is True
        assert schema.is_allowed_edge("Dish", "HAS_STEP", "Step") is True
        assert schema.is_allowed_edge("Technique", "APPLIES_TO", "Dish") is True
        # 非法方向 / 未知关系
        assert schema.is_allowed_edge("Step", "REQUIRES", "Dish") is False
        assert schema.is_allowed_edge("Dish", "RELATED_TO", "Ingredient") is False


class TestNormalizeAndAliases:
    """规范化与别名归并（07 §5 别名归并用例）。"""

    def test_normalize_strips_decorative_prefix(self) -> None:
        assert normalize_name("新鲜的鲈鱼") == "鲈鱼"
        assert normalize_name("冷冻 鲈鱼") == "鲈鱼"

    def test_normalize_fullwidth_and_case(self) -> None:
        assert normalize_name("Tomato") == "tomato"
        assert normalize_name("ｔｏｍａｔｏ") == "tomato"
        assert normalize_name("  Bass ") == "bass"

    def test_alias_lookup_hits(self) -> None:
        table = load_alias_table()
        assert table.lookup("西红柿") == ("番茄", "Ingredient")
        assert table.lookup("tomato") == ("番茄", "Ingredient")
        assert table.lookup("bass") == ("鲈鱼", "Ingredient")
        assert table.lookup("steaming") == ("清蒸", "Technique")
        # canonical 自身可查
        assert table.lookup("番茄") == ("番茄", "Ingredient")
        assert table.lookup("不存在的实体") is None

    def test_alias_table_from_groups(self) -> None:
        table = AliasTable(
            [{"canonical": "土豆", "type": "Ingredient", "aliases": ["马铃薯", "potato"]}]
        )
        assert table.lookup("马铃薯") == ("土豆", "Ingredient")
        assert table.lookup("potato") == ("土豆", "Ingredient")


class _FakeEmbedder:
    """Embedding 测试替身：名称 → 固定向量。"""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        """初始化替身。

        Args:
            vectors: 名称到向量的映射（未知名返回 [1,0]）。
        """
        self.vectors = vectors

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """按映射返回 dense 向量。"""
        return EmbeddingResult(
            dense=[self.vectors.get(t, [1.0, 0.0]) for t in texts]
        )


def _vec(sim: float) -> list[float]:
    """构造与 [1,0] 余弦相似度为 sim 的单位向量。"""
    return [sim, math.sqrt(max(0.0, 1.0 - sim * sim))]


class TestEntityResolver:
    """G2 对齐链路：别名 → 向量消歧 → 白名单/开放区。"""

    @pytest.mark.asyncio
    async def test_alias_hit_marks_core_approved(self) -> None:
        schema = load_graph_schema()
        resolver = EntityResolver(schema, load_alias_table())
        results = await resolver.resolve(
            [EntityMention(name="西红柿", type="Ingredient")]
        )
        assert results[0].canonical_name == "番茄"
        assert results[0].zone == "core"
        assert results[0].status == "approved"
        assert results[0].type == "Ingredient"

    @pytest.mark.asyncio
    async def test_whitelist_type_marks_core_pending(self) -> None:
        schema = load_graph_schema()
        resolver = EntityResolver(schema, AliasTable([]))
        results = await resolver.resolve(
            [EntityMention(name="宫保鸡丁", type="Dish")]
        )
        assert results[0].canonical_name == "宫保鸡丁"
        assert results[0].zone == "core"
        assert results[0].status == "pending"

    @pytest.mark.asyncio
    async def test_unknown_type_goes_open_zone(self) -> None:
        schema = load_graph_schema()
        resolver = EntityResolver(schema, AliasTable([]))
        results = await resolver.resolve(
            [EntityMention(name="某餐厅", type="Restaurant")]
        )
        assert results[0].zone == "open"
        assert results[0].type == "Other"  # J12 开放区默认类型
        assert results[0].status == "pending"

    @pytest.mark.asyncio
    async def test_vector_merge_above_threshold(self) -> None:
        """相似度 ≥ 0.92 且类型相同 → 自动归并（07 §5）。"""
        schema = load_graph_schema()
        embedder = _FakeEmbedder({"淡水鲈": [1.0, 0.0], "鲈鱼": _vec(0.95)})
        resolver = EntityResolver(
            schema,
            AliasTable([]),
            embedding_service=embedder,
            known_canonicals={"鲈鱼": "Ingredient"},
        )
        results = await resolver.resolve(
            [EntityMention(name="淡水鲈", type="Ingredient")]
        )
        assert results[0].canonical_name == "鲈鱼"  # 归并到规范实体
        assert results[0].zone == "core"
        assert results[0].status == "approved"
        assert results[0].similarity == pytest.approx(0.95, abs=1e-6)
        assert results[0].needs_review is False

    @pytest.mark.asyncio
    async def test_gray_zone_goes_review_queue(self) -> None:
        """[0.80, 0.92) 灰区 → 人工审核队列（07 §5）。"""
        schema = load_graph_schema()
        embedder = _FakeEmbedder({"疑似鲈鱼": [1.0, 0.0], "鲈鱼": _vec(0.85)})
        resolver = EntityResolver(
            schema,
            AliasTable([]),
            embedding_service=embedder,
            known_canonicals={"鲈鱼": "Ingredient"},
        )
        results = await resolver.resolve(
            [EntityMention(name="疑似鲈鱼", type="Ingredient")]
        )
        assert results[0].needs_review is True
        assert results[0].status == "pending"
        assert results[0].similarity == pytest.approx(0.85, abs=1e-6)

    @pytest.mark.asyncio
    async def test_type_mismatch_not_merged(self) -> None:
        """相似度达标但类型不同 → 不归并。"""
        schema = load_graph_schema()
        embedder = _FakeEmbedder({"鲈鱼菜品": [1.0, 0.0], "鲈鱼": _vec(0.95)})
        resolver = EntityResolver(
            schema,
            AliasTable([]),
            embedding_service=embedder,
            known_canonicals={"鲈鱼": "Ingredient"},
        )
        results = await resolver.resolve(
            [EntityMention(name="鲈鱼菜品", type="Dish")]
        )
        assert results[0].canonical_name == "鲈鱼菜品"  # 未归并
        assert results[0].zone == "core"  # Dish 在白名单
        assert results[0].status == "pending"

    @pytest.mark.asyncio
    async def test_low_similarity_no_review(self) -> None:
        """相似度低于灰区下界 → 无归并无审核。"""
        schema = load_graph_schema()
        embedder = _FakeEmbedder({"全新实体": [1.0, 0.0], "鲈鱼": _vec(0.5)})
        resolver = EntityResolver(
            schema,
            AliasTable([]),
            embedding_service=embedder,
            known_canonicals={"鲈鱼": "Ingredient"},
        )
        results = await resolver.resolve(
            [EntityMention(name="全新实体", type="Ingredient")]
        )
        assert results[0].needs_review is False
        assert results[0].canonical_name == "全新实体"


class TestCosineSimilarity:
    """余弦相似度边界。"""

    def test_identical_vectors(self) -> None:
        assert cosine_similarity([1.0, 2.0], [1.0, 2.0]) == pytest.approx(1.0)

    def test_zero_vector(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


class TestNeo4jConstraints:
    """04 §5.3 约束与索引（集成，Neo4j 不可达时跳过）。"""

    @pytest.mark.asyncio
    async def test_ensure_constraints_and_verify(self) -> None:
        client = Neo4jClient("bolt://localhost:7687", "neo4j", "password")
        if not await client.check_health():
            pytest.skip("Neo4j 不可达，集成用例跳过")
        try:
            await client.ensure_constraints()
            rows = await client.execute_cypher("SHOW CONSTRAINTS YIELD name RETURN name")
            names = {r["name"] for r in rows}
            assert "entity_canonical" in names
            assert "chunk_id" in names
            assert "community_id" in names
        finally:
            await client.close()
