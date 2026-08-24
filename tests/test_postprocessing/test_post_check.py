"""后处理分级校验测试（单元 7.1 S3，07 §6 断言）。

断言：分级启用矩阵（standard/fast 跳过、deep 启用）；低分触发幻觉
检测；评分/检测 LLM 失败回退放行（D5，重试耗尽 degraded 语义）。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import RetrievalResult, SourceKind
from app.postprocessing.faithfulness_scorer import FaithfulnessScorer
from app.postprocessing.hallucination_detector import HallucinationDetector
from app.postprocessing.post_check import run_post_check


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
        self.calls = 0

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        """模拟 chat。"""
        self.calls += 1
        if self.raise_exc:
            raise RuntimeError("judge down")

        class _Resp:
            content = self.content
            usage = None

        return _Resp()


def _evidence() -> list[RetrievalResult]:
    """构造证据。"""
    return [
        RetrievalResult(
            result_id="e1",
            chunk_id=None,
            content="清蒸鲈鱼需要蒸八分钟",
            score=0.9,
            source=SourceKind.DENSE,
            doc_id=None,
            metadata={},
        )
    ]


class TestTieredEnablement:
    """分级启用矩阵（准出）。"""

    @pytest.mark.asyncio
    async def test_fast_skipped(self) -> None:
        result = await run_post_check("答案", _evidence(), "fast")
        assert result.enabled is False
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_standard_skipped(self) -> None:
        result = await run_post_check("答案", _evidence(), "standard")
        assert result.enabled is False

    @pytest.mark.asyncio
    async def test_deep_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = FakeLLM('{"score": 0.95}')
        monkeypatch.setattr(
            "app.postprocessing.faithfulness_scorer._get_llm", lambda: fake
        )
        result = await run_post_check("答案", _evidence(), "deep")
        assert result.enabled is True
        assert result.score == pytest.approx(0.95)
        assert result.report is None  # 高分不触发检测


class TestHallucinationTrigger:
    """低分触发幻觉检测。"""

    @pytest.mark.asyncio
    async def test_low_score_triggers_detection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.postprocessing.faithfulness_scorer._get_llm",
            lambda: FakeLLM('{"score": 0.3}'),
        )
        monkeypatch.setattr(
            "app.postprocessing.hallucination_detector._get_llm",
            lambda: FakeLLM(
                '{"faithful": false, "unsupported_claims": ["蒸二十分钟"]}'
            ),
        )
        result = await run_post_check("答案说蒸二十分钟", _evidence(), "deep")
        assert result.score == pytest.approx(0.3)
        assert result.report is not None
        assert result.report.has_hallucination is True
        assert result.report.unsupported_claims == ["蒸二十分钟"]


class TestDegradation:
    """LLM 失败回退（D5）。"""

    @pytest.mark.asyncio
    async def test_scorer_failure_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """评分 LLM 不可用 → 回退 1.0 放行。"""
        monkeypatch.setattr(
            "app.postprocessing.faithfulness_scorer._get_llm",
            lambda: FakeLLM("", raise_exc=True),
        )
        scorer = FaithfulnessScorer()
        score = await scorer.score("答案", "证据")
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_detector_failure_fallback_report(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """检测 LLM 不可用 → 回退无幻觉报告。"""
        monkeypatch.setattr(
            "app.postprocessing.hallucination_detector._get_llm",
            lambda: FakeLLM("", raise_exc=True),
        )
        detector = HallucinationDetector()
        report = await detector.detect("答案", "证据")
        assert report.has_hallucination is False

    @pytest.mark.asyncio
    async def test_scorer_clamps_and_rejects_bad_json(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.postprocessing.faithfulness_scorer._get_llm",
            lambda: FakeLLM('{"score": 1.7}'),
        )
        scorer = FaithfulnessScorer()
        assert await scorer.score("答案", "证据") == 1.0  # 截断到上界

        monkeypatch.setattr(
            "app.postprocessing.faithfulness_scorer._get_llm",
            lambda: FakeLLM("{bad json"),
        )
        assert await scorer.score("答案", "证据") == 1.0  # 解析失败放行

    def test_threshold_judgement(self) -> None:
        scorer = FaithfulnessScorer(threshold=0.7)
        assert scorer.is_faithful(0.7) is True
        assert scorer.is_faithful(0.69) is False
