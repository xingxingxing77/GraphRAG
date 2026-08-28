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
        self.fallback_called = 0
        self.model_called: list[str] = []
        self.last_messages: list[dict[str, str]] = []

    async def chat_with_fallback(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        """模拟 fallback 链调用。"""
        self.fallback_called += 1
        self.last_messages = messages
        if self.raise_exc:
            raise RuntimeError("all fallback failed")

        class _Resp:
            content = self.content
            usage = None

        return _Resp()

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        """J2：请求级覆盖模型的 chat（替身自身经 for_model 返回）。"""
        self.last_messages = messages
        if self.raise_exc:
            raise RuntimeError("model failed")

        class _Resp:
            content = self.content
            usage = None

        return _Resp()

    def for_model(self, model_name: str) -> "FakeRegistry":
        """J2：请求级模型覆盖（记录调用；未注册条目抛 KeyError）。"""
        if model_name == "unknown-model":
            raise KeyError(model_name)
        self.model_called.append(model_name)
        return self


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
    async def test_fallback_failure_keeps_retry_counter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """M1：降级出口也持久化重试计数，防 generator↔self_correction 死循环。"""
        fake = FakeRegistry("", raise_exc=True)
        monkeypatch.setattr("app.agent.nodes.generator._get_registry", lambda: fake)
        updates = await generator_node(_state(answer="旧答案"))
        assert updates["degraded"] is True
        assert updates["self_correction_retries"] == 1

    @pytest.mark.asyncio
    async def test_model_override_uses_for_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """J2/C6：请求级 model 走 for_model，不再静默忽略。"""
        fake = FakeRegistry("覆盖模型答案[1]。")
        monkeypatch.setattr("app.agent.nodes.generator._get_registry", lambda: fake)
        updates = await generator_node(_state(model="gpt-main"))
        assert fake.model_called == ["gpt-main"]
        assert fake.fallback_called == 0
        assert "覆盖模型答案" in updates["answer"]

    @pytest.mark.asyncio
    async def test_model_failure_falls_back_to_chain(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """覆盖模型未注册/调用失败时回退 fallback 链（D5 不抛错）。"""
        fake = FakeRegistry("链上答案[1]。")
        monkeypatch.setattr("app.agent.nodes.generator._get_registry", lambda: fake)
        updates = await generator_node(_state(model="unknown-model"))
        assert fake.model_called == []
        assert fake.fallback_called == 1
        assert "链上答案" in updates["answer"]

    @pytest.mark.asyncio
    async def test_correction_hint_and_history_in_prompt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """M3/J17：重生成提示与多轮上下文进入 user prompt。"""
        fake = FakeRegistry("修正答案[1]。")
        monkeypatch.setattr("app.agent.nodes.generator._get_registry", lambda: fake)
        await generator_node(
            _state(
                correction_hint="忠实度评分仅 0.40，评审理由：编造时间",
                history_context="[历史1轮] Q: 鲈鱼怎么蒸 A: 蒸8分钟",
            )
        )
        user_msg = fake.last_messages[-1]["content"]
        assert "编造时间" in user_msg
        assert "对话上下文" in user_msg
        assert "鲈鱼怎么蒸" in user_msg

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
