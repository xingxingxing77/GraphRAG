"""G5 社区检测与摘要测试（单元 2.6 S3，07 §5 断言）。

断言：社区树完整性（父子闭合）；>20% 变更触发重算（J14 逻辑桩）；
摘要降级路径；Neo4j 社区子图写入（集成）。
"""

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import CommunityRecord
from app.db.neo4j_client import Neo4jClient
from app.pipeline.graph_construction.community import (
    LeidenDetector,
    should_recompute,
)
from app.pipeline.graph_construction.graph_writer import GraphWriter
from app.pipeline.graph_construction.schema import load_graph_schema
from app.pipeline.graph_construction.summarizer import CommunitySummarizer

_TEST_PREFIX = "__test_2_6__"


def _two_cluster_graph() -> tuple[list[str], list[tuple[str, str]]]:
    """构造两个明显聚类的图（各 4 节点 + 1 跨簇桥边）。"""
    nodes = [f"{_TEST_PREFIX}a{i}" for i in range(4)] + [
        f"{_TEST_PREFIX}b{i}" for i in range(4)
    ]
    edges: list[tuple[str, str]] = []
    for i in range(3):
        edges.append((f"{_TEST_PREFIX}a{i}", f"{_TEST_PREFIX}a{i + 1}"))
        edges.append((f"{_TEST_PREFIX}b{i}", f"{_TEST_PREFIX}b{i + 1}"))
    # 跨簇桥边（保持连通）
    edges.append((f"{_TEST_PREFIX}a3", f"{_TEST_PREFIX}b0"))
    return nodes, edges


class TestLeidenDetector:
    """社区树完整性（父子闭合，07 §5）。"""

    def test_detect_produces_communities(self) -> None:
        nodes, edges = _two_cluster_graph()
        records = LeidenDetector().detect(nodes, edges, community_prefix=_TEST_PREFIX)
        assert records, "应产出社区"
        leaves = [r for r in records if r.level == 0]
        assert leaves, "应有叶子社区"
        # 全部节点被覆盖（叶子成员并集 == 节点集）
        covered = {m for leaf in leaves for m in leaf.members}
        assert covered == set(nodes)

    def test_parent_child_closure(self) -> None:
        """父子闭合：叶子的 parent_id 必须指向存在的父社区。"""
        nodes, edges = _two_cluster_graph()
        records = LeidenDetector().detect(nodes, edges, community_prefix=_TEST_PREFIX)
        ids = {r.community_id for r in records}
        parents = [r for r in records if r.level > 0]
        for leaf in (r for r in records if r.level == 0):
            if leaf.parent_id is not None:
                assert leaf.parent_id in ids
        # 若存在父层，每个父社区至少有一个子社区
        for parent in parents:
            children = [r for r in records if r.parent_id == parent.community_id]
            assert children, f"父社区 {parent.community_id} 无子社区"

    def test_empty_graph_returns_empty(self) -> None:
        assert LeidenDetector().detect([], []) == []


class TestRecomputeTrigger:
    """J14 全量重算触发（>20% 变更）。"""

    def test_over_threshold_triggers(self) -> None:
        assert should_recompute(member_count=100, changed_count=21) is True

    def test_under_threshold_no_trigger(self) -> None:
        assert should_recompute(member_count=100, changed_count=20) is False
        assert should_recompute(member_count=100, changed_count=5) is False

    def test_empty_system(self) -> None:
        assert should_recompute(member_count=0, changed_count=1) is True
        assert should_recompute(member_count=0, changed_count=0) is False


class TestCommunitySummarizer:
    """摘要器（无 LLM 降级抽取式）。"""

    @pytest.mark.asyncio
    async def test_extractive_fallback_summary(self) -> None:
        summarizer = CommunitySummarizer(llm_client=None)
        summary = await summarizer.summarize_leaf(["鲈鱼", "姜", "葱"], [])
        assert "鲈鱼" in summary
        assert "3 个实体" in summary or "姜" in summary

    @pytest.mark.asyncio
    async def test_hierarchy_summaries_filled(self) -> None:
        summarizer = CommunitySummarizer(llm_client=None)
        records = [
            CommunityRecord(community_id="c-l0-0", level=0, members=["甲", "乙"]),
            CommunityRecord(community_id="c-l0-1", level=0, members=["丙", "丁"]),
            CommunityRecord(community_id="c-l1-0", level=1, members=["甲", "乙", "丙", "丁"]),
        ]
        records[0] = records[0].model_copy(update={"parent_id": "c-l1-0"})
        records[1] = records[1].model_copy(update={"parent_id": "c-l1-0"})
        result = await summarizer.summarize_hierarchy(records)
        assert all(r.summary for r in result), "全部社区应有摘要"
        parent = next(r for r in result if r.level == 1)
        assert parent.summary, "父社区摘要应聚合子层"


class TestCommunityNeo4jWrite:
    """Neo4j 社区子图写入（集成，不可达时跳过）。"""

    @pytest.mark.asyncio
    async def test_write_and_query_communities(self) -> None:
        client = Neo4jClient("bolt://localhost:7687", "neo4j", "password")
        if not await client.check_health():
            pytest.skip("Neo4j 不可达，集成用例跳过")
        writer = GraphWriter(client, load_graph_schema())
        records = [
            CommunityRecord(
                community_id=f"{_TEST_PREFIX}c-l0-0",
                level=0,
                members=[f"{_TEST_PREFIX}a0", f"{_TEST_PREFIX}a1"],
                summary="测试叶子社区摘要",
            ),
            CommunityRecord(
                community_id=f"{_TEST_PREFIX}c-l1-0",
                level=1,
                members=[f"{_TEST_PREFIX}a0", f"{_TEST_PREFIX}a1"],
                summary="测试父社区摘要",
            ),
        ]
        records[0] = records[0].model_copy(
            update={"parent_id": f"{_TEST_PREFIX}c-l1-0"}
        )
        try:
            await writer.write_communities(records)
            rows = await client.execute_cypher(
                "MATCH (m:Community) WHERE m.community_id STARTS WITH $p "
                "RETURN count(m) AS c",
                {"p": _TEST_PREFIX},
            )
            assert rows[0]["c"] == 2
            # PART_OF 层级边存在
            part_of = await client.execute_cypher(
                "MATCH (c:Community {community_id: $child})"
                "-[:PART_OF]->(p:Community {community_id: $parent}) "
                "RETURN count(*) AS c",
                {
                    "child": f"{_TEST_PREFIX}c-l0-0",
                    "parent": f"{_TEST_PREFIX}c-l1-0",
                },
            )
            assert part_of[0]["c"] == 1
        finally:
            await client.execute_cypher(
                "MATCH (m:Community) WHERE m.community_id STARTS WITH $p "
                "DETACH DELETE m",
                {"p": _TEST_PREFIX},
            )
            await client.close()
