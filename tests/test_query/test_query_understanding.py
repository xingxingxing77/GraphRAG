"""查询理解层测试（单元 6.1/6.2 S3，07 §5/§6 E-15 断言）。

断言：四字段完整性；解析失败重试 1 次后走原始查询（D5 不标记）；
chitchat 规则前置零 LLM；D4 定档矩阵 + auto 回写 + 显式覆盖；
standard→deep Rerank 置信度升级判定。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import IntentType
from app.query.router import (
    _parse_qu_output,
    resolve_latency_tier,
    rule_chitchat,
    should_upgrade_to_deep,
    understand_query,
)


class FakeLLM:
    """LLM 测试替身：按序返回响应。"""

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


class TestRuleShortCircuit:
    """chitchat 规则前置（零 LLM，S-02 断言基础）。"""

    def test_greeting_hits(self) -> None:
        assert rule_chitchat("你好") is True
        assert rule_chitchat("Hello！") is True

    def test_empty_query_hits(self) -> None:
        assert rule_chitchat("   ") is True

    def test_long_substantive_query_misses(self) -> None:
        assert rule_chitchat("清蒸鲈鱼的具体做法和火候注意事项是什么") is False

    def test_question_word_blocks_short_circuit(self) -> None:
        assert rule_chitchat("怎么做") is False

    @pytest.mark.asyncio
    async def test_rule_hit_zero_llm_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """规则短路命中时不调 LLM（LangSmith 无 query_understanding span）。"""
        fake = FakeLLM(["unused"])
        monkeypatch.setattr("app.query.router._get_llm", lambda: fake)
        result = await understand_query("你好")
        assert fake.calls == 0
        assert result.intent == IntentType.CHITCHAT
        assert result.rule_short_circuit is True


class TestMergedCall:
    """M2 合并式结构化调用（四字段）。"""

    @pytest.mark.asyncio
    async def test_four_fields_complete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeLLM(
            [
                '{"intent": "multi_hop", "rewritten_query": "清蒸鲈鱼做法与火候",'
                ' "subqueries": ["鲈鱼蒸制时间", "清蒸调味"], '
                '"entities": [{"name": "鲈鱼", "type": "食材"}]}'
            ]
        )
        monkeypatch.setattr("app.query.router._get_llm", lambda: fake)
        result = await understand_query("清蒸鲈鱼怎么做好吃？要注意什么火候？")
        assert fake.calls == 1  # 单次合并调用
        assert result.intent == IntentType.MULTI_HOP
        assert result.rewritten_query == "清蒸鲈鱼做法与火候"
        assert result.subqueries == ["鲈鱼蒸制时间", "清蒸调味"]
        assert result.entities[0].name == "鲈鱼"

    @pytest.mark.asyncio
    async def test_parse_failure_retry_then_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """解析失败重试 1 次 → 再失败跳过改写用原始查询（D5）。"""
        fake = FakeLLM(["{bad json}", "{still bad}"])
        monkeypatch.setattr("app.query.router._get_llm", lambda: fake)
        result = await understand_query("鲈鱼的蛋白质含量与其他鱼类对比")
        assert fake.calls == 2  # 重试 1 次
        assert result.rewritten_query == "鲈鱼的蛋白质含量与其他鱼类对比"  # 原始查询兜底
        assert result.intent == IntentType.FACTOID

    @pytest.mark.asyncio
    async def test_retry_recovers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeLLM(
            ["{bad}", '{"intent": "factoid", "rewritten_query": "鲈鱼蛋白质含量"}']
        )
        monkeypatch.setattr("app.query.router._get_llm", lambda: fake)
        result = await understand_query("鲈鱼蛋白质多少？")
        assert fake.calls == 2
        assert result.rewritten_query == "鲈鱼蛋白质含量"

    def test_parse_rejects_invalid_intent(self) -> None:
        assert _parse_qu_output('{"intent": "unknown", "rewritten_query": "x"}') is None
        assert _parse_qu_output('{"intent": "factoid"}') is None  # 缺 rewritten
        assert _parse_qu_output("{bad") is None


class TestTierRouting:
    """D4 三档路由（6.2，E-15 意图路由矩阵）。"""

    @pytest.mark.parametrize(
        ("intent", "expected"),
        [
            (IntentType.CHITCHAT, "fast"),
            (IntentType.FACTOID, "standard"),
            (IntentType.MULTI_HOP, "deep"),
            (IntentType.COMPARISON, "deep"),
            (IntentType.GLOBAL_SUMMARY, "deep"),
        ],
    )
    def test_auto_tier_matrix(self, intent: IntentType, expected: str) -> None:
        assert resolve_latency_tier(intent, "auto") == expected

    def test_explicit_tier_overrides(self) -> None:
        """latency_tier 参数覆盖生效（准出）。"""
        assert resolve_latency_tier(IntentType.FACTOID, "deep") == "deep"
        assert resolve_latency_tier(IntentType.MULTI_HOP, "fast") == "fast"

    def test_unknown_requested_treated_as_auto(self) -> None:
        assert resolve_latency_tier(IntentType.FACTOID, "bogus") == "standard"


class TestStandardToDeepUpgrade:
    """standard→deep 升级（v3.1：Rerank 置信度依据，complexity 废弃）。"""

    def test_low_confidence_upgrades(self) -> None:
        assert should_upgrade_to_deep([0.1, 0.2], rerank_threshold=0.3) is True

    def test_high_confidence_stays(self) -> None:
        assert should_upgrade_to_deep([0.8, 0.9], rerank_threshold=0.3) is False

    def test_empty_scores_upgrades(self) -> None:
        assert should_upgrade_to_deep([], rerank_threshold=0.3) is True
