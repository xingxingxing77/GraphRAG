"""Reflector 节点与 A2 短路测试（单元 5.4 S3，07 §5 断言）。

断言：结构化输出解析；解析失败重试路径（重试耗尽兜底 sufficient）；
A2 短路四条件真值表（短路时路由 generator，无 reflector 执行）。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.agent.nodes.reflector import _parse_feedback, reflector_node
from app.agent.routers import (
    EVIDENCE_ENOUGH_COUNT,
    REFLECT_SKIP_THRESHOLD,
    route_reflect_entry,
)
from app.core.models import RetrievalResult, SourceKind


class FakeLLM:
    """LLM 测试替身：按序返回多个响应。"""

    def __init__(self, contents: list[str]) -> None:
        """初始化替身。

        Args:
            contents: 每次 chat 依次返回的文本。
        """
        self.contents = list(contents)
        self.calls = 0

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        """模拟 chat。"""
        idx = min(self.calls, len(self.contents) - 1)
        self.calls += 1

        class _Resp:
            content = self.contents[idx]
            usage = None

        return _Resp()


def _evidence(rid: str, score: float) -> RetrievalResult:
    """构造证据。"""
    return RetrievalResult(
        result_id=rid,
        chunk_id=None,
        content=f"证据 {rid}",
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
        "retrieved_evidence": [_evidence("e1", 0.5)],
        "token_budget_exhausted": False,
    }
    state.update(overrides)
    return state


class TestReflectorOutput:
    """结构化输出（C8 契约）。"""

    @pytest.mark.asyncio
    async def test_insufficient_drives_loop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeLLM(
            ['{"sufficient": false, "missing_aspects": ["火候"], "followup_queries": ["蒸制时间"]}']
        )
        monkeypatch.setattr("app.agent.nodes.reflector._get_llm", lambda: fake)
        updates = await reflector_node(_state())
        fb = updates["reflect_feedback"]
        assert fb.sufficient is False
        assert fb.followup_queries == ["蒸制时间"]
        assert updates["needs_more_retrieval"] is True

    @pytest.mark.asyncio
    async def test_sufficient_stops_loop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeLLM(['{"sufficient": true}'])
        monkeypatch.setattr("app.agent.nodes.reflector._get_llm", lambda: fake)
        updates = await reflector_node(_state())
        assert updates["reflect_feedback"].sufficient is True
        assert updates["needs_more_retrieval"] is False

    @pytest.mark.asyncio
    async def test_empty_evidence_skips_llm(self) -> None:
        updates = await reflector_node(_state(retrieved_evidence=[]))
        assert updates["reflect_feedback"].sufficient is True
        assert updates["needs_more_retrieval"] is False


class TestParseRetry:
    """输出解析失败重试路径。"""

    @pytest.mark.asyncio
    async def test_retry_recovers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeLLM(["{bad json}", '{"sufficient": false, "followup_queries": ["q"]}'])
        monkeypatch.setattr("app.agent.nodes.reflector._get_llm", lambda: fake)
        updates = await reflector_node(_state())
        assert fake.calls == 2  # 第一次失败重试
        assert updates["reflect_feedback"].sufficient is False

    @pytest.mark.asyncio
    async def test_retry_exhausted_falls_back_sufficient(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = FakeLLM(["{bad}", "{still bad}"])
        monkeypatch.setattr("app.agent.nodes.reflector._get_llm", lambda: fake)
        updates = await reflector_node(_state())
        assert fake.calls == 2
        # 兜底 sufficient=True，不无限回环
        assert updates["reflect_feedback"].sufficient is True
        assert updates["needs_more_retrieval"] is False

    def test_parse_feedback_variants(self) -> None:
        assert _parse_feedback("{bad") is None
        assert _parse_feedback('{"no_key": 1}') is None
        fb = _parse_feedback('{"sufficient": true}')
        assert fb is not None and fb.sufficient is True


class TestA2ShortCircuit:
    """A2 短路真值表（短路 → generator，reflector 不执行）。"""

    def test_fast_tier_short_circuits(self) -> None:
        assert route_reflect_entry(_state(latency_tier="fast")) == "generator"

    def test_enough_evidence_short_circuits(self) -> None:
        evidence = [_evidence(f"e{i}", 0.3) for i in range(EVIDENCE_ENOUGH_COUNT)]
        assert route_reflect_entry(_state(retrieved_evidence=evidence)) == "generator"

    def test_high_avg_score_short_circuits(self) -> None:
        evidence = [_evidence("e1", REFLECT_SKIP_THRESHOLD + 0.1)]
        assert route_reflect_entry(_state(retrieved_evidence=evidence)) == "generator"

    def test_low_score_few_evidence_goes_reflector(self) -> None:
        evidence = [_evidence("e1", 0.3), _evidence("e2", 0.2)]
        assert route_reflect_entry(_state(retrieved_evidence=evidence)) == "reflector"

    def test_budget_exhausted_overrides(self) -> None:
        assert (
            route_reflect_entry(_state(token_budget_exhausted=True)) == "generator"
        )
