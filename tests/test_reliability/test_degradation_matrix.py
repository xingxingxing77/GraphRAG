"""D5 降级矩阵故障注入测试（单元 9.1 S3，07 §6 E-07~E-11b）。

断言：六故障场景降级路径与 degraded_reasons 上报；X-Degraded
透传链（图内 → values → 响应头）枚举校验完整。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
import pytest
from fastapi import Response

# --- 本地模块 ---
from app.agent.nodes.generator import generator_node
from app.agent.nodes.load_memory import load_memory_node
from app.agent.nodes.tool_router import tool_router_node
from app.agent.routers import _degrade, route_after_tool_router
from app.api.degraded import (
    apply_degraded_header,
    build_degraded_header,
    reasons_from_values,
)
from app.core.models import PlanStep, RetrievalResult, SourceKind
from app.reranking.reranker import BGEReranker


class FakeRetriever:
    """检索器替身（可注入故障，带 error_count）。"""

    def __init__(self, fail: bool = False) -> None:
        """初始化替身。

        Args:
            fail: retrieve 是否抛异常。
        """
        self.fail = fail
        self.error_count = 0

    async def retrieve(self, query: str, top_k: int, filters: Any = None):
        """模拟检索（故障时模拟真实检索器的内部降级计数）。"""
        if self.fail:
            self.error_count += 1
            return []
        return [
            RetrievalResult(
                result_id=f"r:{query}",
                chunk_id=None,
                content="证据",
                score=0.8,
                source=SourceKind.DENSE,
                doc_id=None,
                metadata={},
            )
        ]


def _state(**overrides: Any) -> dict[str, Any]:
    """构造最小状态。"""
    state: dict[str, Any] = {
        "query": "清蒸鲈鱼怎么做？",
        "latency_tier": "standard",
        "plan": [PlanStep(step_id="step-1", tool="dense", query="清蒸鲈鱼做法")],
        "current_step": 0,
        "retrieved_evidence": [],
        "retrieval_rounds": 0,
        "tool_call_cache": {},
        "token_budget_exhausted": False,
    }
    state.update(overrides)
    return state


class TestE07NoGraph:
    """E-07：Neo4j 不可达 → 图谱系降级 + no-graph 上报。"""

    @pytest.mark.asyncio
    async def test_graph_family_failure_reports_no_graph(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hub: dict[str, Any] = {
            "dense": FakeRetriever(),
            "graph": FakeRetriever(fail=True),
            "global": FakeRetriever(fail=True),
            "fulltext": FakeRetriever(fail=True),
        }

        async def fake_hub():
            return hub

        monkeypatch.setattr(
            "app.agent.nodes.tool_router._get_retriever_hub", fake_hub
        )
        state = _state(
            plan=[
                PlanStep(step_id="step-1", tool="dense", query="q1"),
                PlanStep(step_id="step-2", tool="graph", query="q2"),
            ]
        )
        updates = await tool_router_node(state)
        assert updates["degraded_reasons"] == ["no-graph"]
        # dense 路不受图谱故障影响（E-07：仅 dense+sparse 检索仍工作）
        assert len(updates["retrieved_evidence"]) >= 1

    @pytest.mark.asyncio
    async def test_no_graph_reason_absent_when_healthy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_hub():
            return {"dense": FakeRetriever()}

        monkeypatch.setattr(
            "app.agent.nodes.tool_router._get_retriever_hub", fake_hub
        )
        updates = await tool_router_node(_state())
        assert "degraded_reasons" not in updates


class TestE08NoRerank:
    """E-08：rerank 超时 → 粗排原序 + no-rerank。"""

    @pytest.mark.asyncio
    async def test_slow_rerank_degrades(self) -> None:
        import time

        def slow_fn(pairs):
            time.sleep(1.0)
            return [1.0] * len(pairs)

        reranker = BGEReranker(score_fn=slow_fn, timeout_s=0.05)
        docs = [
            RetrievalResult(
                result_id="d1", chunk_id=None, content="证据", score=0.9,
                source=SourceKind.DENSE, doc_id=None, metadata={},
            )
        ]
        ranked = await reranker.rerank("q", docs, top_k=1)
        assert reranker.last_degraded is True
        assert ranked[0][1] == pytest.approx(0.9)  # 粗排原序分


class TestE09NoMemory:
    """E-09：记忆层故障 → 主链路不阻塞 + no-memory 上报。"""

    @pytest.mark.asyncio
    async def test_memory_failure_reports_no_memory(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(state):
            raise RuntimeError("redis down")

        monkeypatch.setattr(
            "app.agent.nodes.load_memory._load_context", boom
        )
        updates = await load_memory_node(_state())
        assert updates["degraded_reasons"] == ["no-memory"]
        assert "query" not in updates  # 原样放行不注入


class TestE10LlmFallback:
    """E-10：generator 主备全败 → 降级短答 + llm-fallback。"""

    @pytest.mark.asyncio
    async def test_fallback_all_failed_reports_reason(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class DeadRegistry:
            async def chat_with_fallback(self, messages, **kwargs):
                raise RuntimeError("all models down")

        monkeypatch.setattr(
            "app.agent.nodes.generator._get_registry", lambda: DeadRegistry()
        )
        updates = await generator_node(_state())
        assert updates["degraded"] is True
        assert updates["degraded_reasons"] == ["llm-fallback"]
        assert updates["answer"]  # 降级轻量回答非空


class TestE11bBudgetExhausted:
    """E-11b：预算耗尽 → budget-exhausted 降级作答而非抛错。"""

    def test_degrade_reports_budget_reason(self) -> None:
        update = _degrade(_state(), reason="budget-exhausted")
        assert update["degraded"] is True
        assert update["degraded_reasons"] == ["budget-exhausted"]

    def test_budget_exhausted_routes_to_generator(self) -> None:
        state = _state(token_budget_exhausted=True)
        assert route_after_tool_router(state) == "generator"


class TestXDegradedPassthrough:
    """X-Degraded 透传链（图内 → values → 响应头）。"""

    def test_header_builds_from_valid_reasons(self) -> None:
        header = build_degraded_header(["no-graph", "no-rerank"])
        assert header == "no-graph,no-rerank"

    def test_unknown_reasons_stripped(self) -> None:
        header = build_degraded_header(["no-graph", "bogus-reason"])
        assert header == "no-graph"

    def test_all_unknown_returns_none(self) -> None:
        assert build_degraded_header(["bogus"]) is None
        assert build_degraded_header([]) is None
        assert build_degraded_header(None) is None

    def test_duplicates_deduped(self) -> None:
        assert build_degraded_header(["no-cache", "no-cache"]) == "no-cache"

    def test_apply_header_sets_response_header(self) -> None:
        resp = Response(content="ok")
        apply_degraded_header(resp, ["no-memory"])
        assert resp.headers["X-Degraded"] == "no-memory"

    def test_apply_header_no_degradation_no_header(self) -> None:
        resp = Response(content="ok")
        apply_degraded_header(resp, [])
        assert "X-Degraded" not in resp.headers

    def test_reasons_from_values_extraction(self) -> None:
        values = {"degraded_reasons": ["no-graph"], "answer": "x"}
        assert reasons_from_values(values) == ["no-graph"]
        assert reasons_from_values({"answer": "x"}) == []


class TestReducerMerge:
    """degraded_reasons 通道 reducer 语义。"""

    def test_merge_dedupes_preserving_order(self) -> None:
        from app.agent.state import merge_degraded_reasons

        merged = merge_degraded_reasons(
            ["no-graph"], ["no-rerank", "no-graph", "no-cache"]
        )
        assert merged == ["no-graph", "no-rerank", "no-cache"]
