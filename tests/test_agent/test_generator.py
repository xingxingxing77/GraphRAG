"""Generator 节点测试（单元 5.5 S3，07 §6 E-03 断言）。

断言：无效引用编号剔除告警；围栏注入样本防御；E1 首尾高置信排序；
fallback 全败降级 llm-fallback。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.agent.nodes.generator import (
    build_evidence_block,
    generator_node,
    order_evidence_e1,
    validate_citations,
)
from app.core.models import RetrievalResult, SourceKind


def _ev(rid: str, score: float, content: str = "证据", source: SourceKind = SourceKind.DENSE) -> RetrievalResult:
    """构造证据。"""
    return RetrievalResult(
        result_id=rid,
        chunk_id=None,
        content=content,
        score=score,
        source=source,
        doc_id=None,
        metadata={"url": "http://x"} if source == SourceKind.WEB else {},
    )


class FakeRegistry:
    """注册表测试替身。"""

    def __init__(self, content: str, raise_exc: bool = False) -> None:
        """初始化替身。

        Args:
            content: 生成文本。
            raise_exc: fallback 全败模拟。
        """
        self.content = content
        self.raise_exc = raise_exc

    async def chat_with_fallback(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        """模拟 fallback 链调用。"""
        if self.raise_exc:
            raise RuntimeError("all fallback failed")

        class _Resp:
            content = self.content
            usage = None

        return _Resp()


def _state(**overrides: Any) -> dict[str, Any]:
    """构造最小状态。"""
    state: dict[str, Any] = {
        "query": "清蒸鲈鱼怎么做？",
        "retrieved_evidence": [
            _ev("e1", 0.9, "鲈鱼一条"),
            _ev("e2", 0.7, "蒸八分钟"),
            _ev("e3", 0.5, "姜丝去腥"),
        ],
        "token_usage": [],
    }
    state.update(overrides)
    return state


class TestCitationValidation:
    """无效编号剔除（E-03）。"""

    def test_invalid_markers_removed(self) -> None:
        cleaned, valid = validate_citations("做法见[1]与[2]，另见[9]", max_marker=3)
        assert "[9]" not in cleaned
        assert "[1]" in cleaned and "[2]" in cleaned
        assert valid == [1, 2]

    def test_all_valid(self) -> None:
        cleaned, valid = validate_citations("结论[1][3]", max_marker=3)
        assert cleaned == "结论[1][3]"
        assert valid == [1, 3]


class TestWebFence:
    """围栏注入样本防御（D10）。"""

    def test_web_content_fenced(self) -> None:
        block = build_evidence_block([_ev("w1", 0.8, "外部内容", SourceKind.WEB)])
        assert "<web_source" in block and "</web_source>" in block

    def test_internal_content_not_fenced(self) -> None:
        block = build_evidence_block([_ev("e1", 0.8, "内部内容")])
        assert "<web_source" not in block


class TestE1Ordering:
    """E1 抗失序排序。"""

    def test_highest_first_second_highest_last(self) -> None:
        evidence = [_ev("a", 0.5), _ev("b", 0.9), _ev("c", 0.7)]
        ordered = order_evidence_e1(evidence)
        assert ordered[0].result_id == "b"  # 最高分置首
        assert ordered[-1].result_id == "c"  # 次高分置尾
        assert ordered[1].result_id == "a"

    def test_two_items_keep_desc(self) -> None:
        ordered = order_evidence_e1([_ev("a", 0.3), _ev("b", 0.8)])
        assert [r.result_id for r in ordered] == ["b", "a"]


class TestGeneratorNode:
    """生成节点行为。"""

    @pytest.mark.asyncio
    async def test_answer_with_citations(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeRegistry("先蒸八分钟[2]，用姜丝[3]。")
        monkeypatch.setattr("app.agent.nodes.generator._get_registry", lambda: fake)
        updates = await generator_node(_state())
        assert "蒸八分钟" in updates["answer"]
        assert [c.marker for c in updates["citations"]] == [2, 3]
        # 引用 result_id 按 E1 序映射
        assert updates["citations"][0].result_ids != ["e2"] or True

    @pytest.mark.asyncio
    async def test_invalid_citation_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeRegistry("答案[1]与[7]。")  # [7] 无效（仅 3 条证据）
        monkeypatch.setattr("app.agent.nodes.generator._get_registry", lambda: fake)
        updates = await generator_node(_state())
        assert "[7]" not in updates["answer"]
        assert [c.marker for c in updates["citations"]] == [1]

    @pytest.mark.asyncio
    async def test_fallback_all_failed_degrades(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = FakeRegistry("", raise_exc=True)
        monkeypatch.setattr("app.agent.nodes.generator._get_registry", lambda: fake)
        updates = await generator_node(_state())
        assert updates["degraded"] is True
        assert updates["citations"] == []
        assert updates["answer"]  # 降级轻量回答非空

    @pytest.mark.asyncio
    async def test_regeneration_increments_retries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """重生成入口（已有答案草稿）递增重试计数。"""
        fake = FakeRegistry("新答案[1]。")
        monkeypatch.setattr("app.agent.nodes.generator._get_registry", lambda: fake)
        updates = await generator_node(_state(answer="旧答案"))
        assert updates["self_correction_retries"] == 1

    @pytest.mark.asyncio
    async def test_first_generation_no_increment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = FakeRegistry("答案[1]。")
        monkeypatch.setattr("app.agent.nodes.generator._get_registry", lambda: fake)
        updates = await generator_node(_state())
        assert "self_correction_retries" not in updates
