"""graph/global/fulltext/web 检索器测试（单元 3.4 S3，07 §5 断言）。

断言：J6 协同集成（ES 召回 → Neo4j 回投 → 合并）；Tavily mock 正常与
超时两用例；单路失败不阻塞其余路（gather return_exceptions）。
"""

# --- 标准库 ---
import asyncio

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import SourceKind
from app.retrieval.fulltext_retriever import FullTextRetriever
from app.retrieval.global_retriever import GlobalRetriever
from app.retrieval.graph_retriever import GraphRetriever
from app.retrieval.web_retriever import WebRetriever


class FakeNeo4j:
    """Neo4j 测试替身：可控 Cypher 返回。"""

    def __init__(self, rows: list[dict] | None = None, raise_exc: bool = False) -> None:
        """初始化替身。

        Args:
            rows: execute_cypher 返回值。
            raise_exc: 是否抛异常。
        """
        self.rows = rows or []
        self.raise_exc = raise_exc

    async def execute_cypher(self, cypher: str, params: dict | None = None):
        """模拟 Cypher 执行。"""
        if self.raise_exc:
            raise RuntimeError("neo4j down")
        return self.rows


class FakeES:
    """ES 测试替身：可控 search 返回。"""

    def __init__(self, hits: list[dict] | None = None, raise_exc: bool = False) -> None:
        """初始化替身。

        Args:
            hits: search 返回值。
            raise_exc: 是否抛异常。
        """
        self.hits = hits or []
        self.raise_exc = raise_exc

    async def search(self, alias: str, field: str, text: str, top_k: int = 10):
        """模拟 IK match 检索。"""
        if self.raise_exc:
            raise RuntimeError("es down")
        return self.hits


class TestGraphRetriever:
    """graph 检索器（Local Search）。"""

    @pytest.mark.asyncio
    async def test_local_search_one_hop(self) -> None:
        rows = [
            {
                "root": "清蒸鲈鱼",
                "root_type": "DISH",
                "neighbors": [{"rel": "USES", "node": "鲈鱼", "node_type": "INGREDIENT"}],
            }
        ]
        retriever = GraphRetriever(FakeNeo4j(rows=rows))
        results = await retriever.retrieve("清蒸鲈鱼", top_k=5)
        assert len(results) == 1
        assert results[0].source == SourceKind.GRAPH
        assert "清蒸鲈鱼" in results[0].content
        assert "USES" in results[0].content

    @pytest.mark.asyncio
    async def test_neo4j_down_degrades(self) -> None:
        retriever = GraphRetriever(FakeNeo4j(raise_exc=True))
        assert await retriever.retrieve("q", 5) == []
        assert retriever.error_count == 1


class TestGlobalRetriever:
    """global 检索器（社区摘要）。"""

    @pytest.mark.asyncio
    async def test_community_summary_recall(self) -> None:
        rows = [
            {"community_id": "c0", "level": 0, "summary": "本社区覆盖水产菜谱"},
            {"community_id": "c1", "level": 1, "summary": ""},
        ]
        retriever = GlobalRetriever(FakeNeo4j(rows=rows))
        results = await retriever.retrieve("水产", top_k=5)
        assert len(results) == 1  # 空摘要被过滤
        assert results[0].source == SourceKind.GLOBAL
        assert results[0].metadata["source"] == "global"


class TestFullTextJ6:
    """J6 协同（ES → Neo4j 回投）。"""

    @pytest.mark.asyncio
    async def test_es_recall_then_neo4j_expand(self) -> None:
        es_hits = [
            {
                "id": "e1",
                "score": 2.5,
                "source": {"canonical_name": "清蒸鲈鱼", "name": "清蒸鲈鱼", "description": "一道菜"},
            }
        ]
        neo4j_rows = [
            {
                "root": "清蒸鲈鱼",
                "neighbors": [{"rel": "USES", "node": "鲈鱼"}],
            }
        ]
        retriever = FullTextRetriever(FakeES(hits=es_hits), FakeNeo4j(rows=neo4j_rows))
        results = await retriever.retrieve("清蒸鲈鱼", top_k=5)
        assert len(results) == 1
        assert results[0].source == SourceKind.FULLTEXT
        assert "USES" in results[0].content  # 回投扩展生效
        assert results[0].score == 2.5

    @pytest.mark.asyncio
    async def test_es_hit_neo4j_deleted_null_skip(self) -> None:
        """ES 命中但 Neo4j 已删（秒级窗口）→ null-skip，仍返回 ES 原文。"""
        es_hits = [
            {
                "id": "e2",
                "score": 1.0,
                "source": {"canonical_name": "已删实体", "name": "已删实体", "description": "描述"},
            }
        ]
        retriever = FullTextRetriever(FakeES(hits=es_hits), FakeNeo4j(rows=[]))
        results = await retriever.retrieve("已删实体", top_k=5)
        assert len(results) == 1
        assert results[0].content == "描述"  # 回查空则用 ES 原文

    @pytest.mark.asyncio
    async def test_es_down_degrades(self) -> None:
        retriever = FullTextRetriever(FakeES(raise_exc=True), FakeNeo4j())
        assert await retriever.retrieve("q", 5) == []


class TestWebRetriever:
    """web 检索器（J4 双轨，Tavily mock）。"""

    @pytest.mark.asyncio
    async def test_tavily_mock_normal(self) -> None:
        def mock_search(query: str, top_k: int):
            return [
                {"title": "结果1", "content": "网页内容1", "url": "http://a", "score": 0.9},
                {"title": "结果2", "content": "网页内容2", "url": "http://b", "score": 0.8},
            ]

        retriever = WebRetriever(tavily_api_key="fake", search_fn=mock_search)
        results = await retriever.retrieve("清蒸鲈鱼", top_k=5)
        assert len(results) == 2
        for r in results:
            assert r.source == SourceKind.WEB
        assert results[0].metadata["url"] == "http://a"

    @pytest.mark.asyncio
    async def test_timeout_degrades(self) -> None:
        def slow_search(query: str, top_k: int):
            import time

            time.sleep(1.0)
            return []

        retriever = WebRetriever(tavily_api_key="fake", search_fn=slow_search, timeout_s=0.05)
        assert await retriever.retrieve("q", 5) == []
        assert retriever.error_count == 1

    @pytest.mark.asyncio
    async def test_search_fn_exception_degrades(self) -> None:
        def bad_search(query: str, top_k: int):
            raise RuntimeError("tavily error")

        retriever = WebRetriever(tavily_api_key="fake", search_fn=bad_search)
        assert await retriever.retrieve("q", 5) == []


class TestOneFailureNotBlock:
    """单路失败不阻塞其余路（准出）。"""

    @pytest.mark.asyncio
    async def test_gather_mixed(self) -> None:
        ok = GraphRetriever(
            FakeNeo4j(rows=[{"root": "实体", "root_type": "DISH", "neighbors": []}])
        )
        bad = GlobalRetriever(FakeNeo4j(raise_exc=True))
        results = await asyncio.gather(
            ok.retrieve("实体", 5), bad.retrieve("实体", 5), return_exceptions=True
        )
        assert isinstance(results[0], list) and len(results[0]) == 1
        assert isinstance(results[1], list) and results[1] == []
