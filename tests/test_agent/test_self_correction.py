"""Self-Correction 节点测试（单元 5.6 S3，07 §6 E-11b 断言）。

断言：忠实度打分驱动重生成路由；预算耗尽直放行；
judge 不可用放行（D5）；重试限次（retries < 1）。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.agent.nodes.self_correction import _parse_score, self_correction_node
from app.agent.routers import FAITHFULNESS_THRESHOLD, route_after_self_correction
from app.core.models import RetrievalResult, SourceKind


class FakeLLM:
    """judge LLM 测试替身。"""

    def __init__(self, content: str, raise_exc: bool = False) -> None:
        """初始化替身。

        Args:
            content: 返回文本。
            raise_exc: 是否抛异常。
        """
        self.content = content
        self.raise_exc = raise_exc

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        """模拟 chat。"""
        if self.raise_exc:
            raise RuntimeError("judge down")

        class _Resp:
            content = self.content
            usage = None

        return _Resp()


def _state(**overrides: Any) -> dict[str, Any]:
    """构造最小状态。"""
    state: dict[str, Any] = {
        "answer": "清蒸鲈鱼需要蒸八分钟。",
        "retrieved_evidence": [
            RetrievalResult(
                result_id="e1",
                chunk_id=None,
                content="蒸八分钟",
                score=0.9,
                source=SourceKind.DENSE,
                doc_id=None,
                metadata={},
            )
        ],
        "faithfulness_score": 1.0,
        "self_correction_retries": 0,
        "token_budget_exhausted": False,
    }
    state.update(overrides)
    return state


class TestFaithfulnessScoring:
    """忠实度打分与重生成驱动。"""

    @pytest.mark.asyncio
    async def test_low_score_returned_without_increment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """节点仅打分；重试计数由 Generator 重生成入口递增。"""
        fake = FakeLLM('{"score": 0.3, "reason": "编造"}')
        monkeypatch.setattr("app.agent.nodes.self_correction._get_llm", lambda: fake)
        updates = await self_correction_node(_state())
        assert updates["faithfulness_score"] == pytest.approx(0.3)
        assert "self_correction_retries" not in updates

    @pytest.mark.asyncio
    async def test_high_score_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeLLM('{"score": 0.95}')
        monkeypatch.setattr("app.agent.nodes.self_correction._get_llm", lambda: fake)
        updates = await self_correction_node(_state())
        assert updates["faithfulness_score"] == pytest.approx(0.95)
        assert "self_correction_retries" not in updates  # 达标不计数

    @pytest.mark.asyncio
    async def test_low_score_routes_back_to_generator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """E-11b：低分 + retries<1 → 回 generator 重生成。"""
        fake = FakeLLM('{"score": 0.2}')
        monkeypatch.setattr("app.agent.nodes.self_correction._get_llm", lambda: fake)
        updates = await self_correction_node(_state())  # retries 仍 0
        state = _state(faithfulness_score=updates["faithfulness_score"])
        assert route_after_self_correction(state) == "generator"

    @pytest.mark.asyncio
    async def test_retry_exhausted_releases(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """重生成后 retries=1 耗尽，再低分也放行 END。"""
        fake = FakeLLM('{"score": 0.2}')
        monkeypatch.setattr("app.agent.nodes.self_correction._get_llm", lambda: fake)
        # 模拟已重生成一次（Generator 入口递增过）
        updates = await self_correction_node(_state(self_correction_retries=1))
        routed = route_after_self_correction(
            _state(
                faithfulness_score=updates["faithfulness_score"],
                self_correction_retries=1,
            )
        )
        assert routed == "__end__"


class TestBudgetAndDegradation:
    """B4 预算预检与 judge 不可用放行。"""

    @pytest.mark.asyncio
    async def test_budget_exhausted_passes_through(self) -> None:
        updates = await self_correction_node(_state(token_budget_exhausted=True))
        assert updates["faithfulness_score"] == 1.0  # 直放行不校验

    @pytest.mark.asyncio
    async def test_judge_unavailable_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = FakeLLM("", raise_exc=True)
        monkeypatch.setattr("app.agent.nodes.self_correction._get_llm", lambda: fake)
        updates = await self_correction_node(_state())
        assert updates["faithfulness_score"] == 1.0  # D5 放行不阻塞交付

    @pytest.mark.asyncio
    async def test_empty_answer_passes(self) -> None:
        updates = await self_correction_node(_state(answer=""))
        assert updates["faithfulness_score"] == 1.0

    def test_parse_score_clamped(self) -> None:
        assert _parse_score('{"score": 1.5}') == 1.0
        assert _parse_score('{"score": -0.3}') == 0.0
        assert _parse_score("{bad") is None
        assert _parse_score('{"no_score": 1}') is None

    def test_threshold_from_config(self) -> None:
        assert FAITHFULNESS_THRESHOLD == pytest.approx(0.7)
