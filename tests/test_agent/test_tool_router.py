"""ToolRouter 节点测试（单元 5.3 S3，07 §5 断言）。

断言：fan-in 后 retrieval_rounds 统一 +1；E3 memo 命中不二次调用；
B3 prune 后 payload 收敛；direct_answer 零执行；deep 档并行扇出。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.agent.nodes.tool_router import (
    dedupe_by_result_id,
    memo_key,
    prune_evidence,
    tool_router_node,
)
from app.core.models import PlanStep, RetrievalResult, SourceKind


def _result(rid: str, score: float = 0.8, content: str = "证据内容") -> RetrievalResult:
    """构造检索结果。"""
    return RetrievalResult(
        result_id=rid,
        chunk_id=None,
        content=content,
        score=score,
        source=SourceKind.DENSE,
        doc_id=None,
        metadata={},
    )


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
    }
    state.update(overrides)
    return state


class TestFanInRoundCount:
    """fan-in 后 retrieval_rounds 统一 +1。"""

    @pytest.mark.asyncio
    async def test_rounds_increment_once_per_round(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        async def fake_tool(tool: str, query: str, top_k: int):
            calls.append(f"{tool}:{query}")
            return [_result(f"r-{len(calls)}", 0.8)]

        monkeypatch.setattr("app.agent.nodes.tool_router._execute_tool", fake_tool)
        state = _state(
            plan=[
                PlanStep(step_id="step-1", tool="dense", query="q1"),
                PlanStep(step_id="step-2", tool="graph", query="q2"),
            ]
        )
        updates = await tool_router_node(state)
        assert updates["retrieval_rounds"] == 1  # 两步同轮，统一 +1
        assert len(calls) == 2
        assert updates["current_step"] == 2
        assert all(s.status == "done" for s in updates["plan"])

    @pytest.mark.asyncio
    async def test_direct_answer_zero_execution(self) -> None:
        state = _state(
            plan=[PlanStep(step_id="step-1", tool="direct_answer", query="你好")]
        )
        updates = await tool_router_node(state)
        assert updates == {}  # 零执行、不计轮次


class TestMemo:
    """E3 run 内记忆化（memo 命中不二次调用）。"""

    @pytest.mark.asyncio
    async def test_memo_hit_avoids_second_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        call_count = 0

        async def fake_tool(tool: str, query: str, top_k: int):
            nonlocal call_count
            call_count += 1
            return [_result("cached-r", 0.9)]

        monkeypatch.setattr("app.agent.nodes.tool_router._execute_tool", fake_tool)

        # 第一轮：写入 memo
        state = _state()
        u1 = await tool_router_node(state)
        assert call_count == 1
        key = memo_key("dense", "清蒸鲈鱼做法")
        assert key in u1["tool_call_cache"]

        # 第二轮回环重执行同 (tool, query)：命中 memo 不二次调用
        state2 = _state(
            tool_call_cache=u1["tool_call_cache"],
            retrieved_evidence=u1["retrieved_evidence"],
            retrieval_rounds=u1["retrieval_rounds"],
            plan=[PlanStep(step_id="step-1", tool="dense", query="清蒸鲈鱼做法")],
        )
        u2 = await tool_router_node(state2)
        assert call_count == 1  # 未二次调用
        assert u2["retrieval_rounds"] == 2

    def test_memo_key_normalized(self) -> None:
        assert memo_key("dense", "  清蒸鲈鱼 ") == memo_key("dense", "清蒸鲈鱼")
        assert memo_key("dense", "q") != memo_key("sparse", "q")


class TestPrune:
    """B3 轮间修剪（checkpoint payload 收敛）。"""

    def test_prune_removes_low_score_and_dedupes(self) -> None:
        evidence = [
            _result("a", 0.9),
            _result("a", 0.9),  # 重复 result_id
            _result("b", 0.1),  # 低于保留线
            _result("c", 0.5),
        ]
        pruned = prune_evidence(evidence, keep_score=0.25, max_content_chars=600)
        assert [r.result_id for r in pruned] == ["a", "c"]

    def test_prune_truncates_content(self) -> None:
        long_content = "长" * 1000
        evidence = [_result("a", 0.9, content=long_content)]
        pruned = prune_evidence(evidence, keep_score=0.25, max_content_chars=600)
        assert len(pruned[0].content) == 600  # payload 体积收敛

    def test_dedupe_by_result_id(self) -> None:
        merged = dedupe_by_result_id(
            [_result("a"), _result("b"), _result("a")]
        )
        assert [r.result_id for r in merged] == ["a", "b"]


class TestDeepParallelFanout:
    """A1：deep 档无依赖步骤并行扇出。"""

    @pytest.mark.asyncio
    async def test_deep_parallel_executes_all_steps(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        async def fake_tool(tool: str, query: str, top_k: int):
            calls.append(query)
            return [_result(f"r-{query}", 0.8)]

        monkeypatch.setattr("app.agent.nodes.tool_router._execute_tool", fake_tool)
        state = _state(
            latency_tier="deep",
            plan=[
                PlanStep(step_id="step-1", tool="dense", query="q1"),
                PlanStep(step_id="step-2", tool="sparse", query="q2"),
                PlanStep(step_id="step-3", tool="graph", query="q3"),
            ],
        )
        updates = await tool_router_node(state)
        assert set(calls) == {"q1", "q2", "q3"}
        assert updates["retrieval_rounds"] == 1
        assert len(updates["retrieved_evidence"]) == 3
