"""Planner 节点测试（单元 5.2 S3，07 §6 E-02 断言）。

断言：chitchat 直答零工具调用；followup_queries 注入补计划；
JSON 计划解析（非法条目剔除）；LLM 失败回退单步 dense。
"""

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.agent.nodes.planner import _parse_plan, planner_node
from app.core.models import IntentType, PlanStep, ReflectFeedback, TokenUsage


class FakeLLM:
    """LLM 测试替身。"""

    def __init__(self, content: str, raise_exc: bool = False) -> None:
        """初始化替身。

        Args:
            content: chat 返回文本。
            raise_exc: 是否抛异常。
        """
        self.content = content
        self.raise_exc = raise_exc
        self.calls = 0

    async def chat(self, messages, **kwargs):  # noqa: ANN001, ANN201
        """模拟 chat。"""
        self.calls += 1
        if self.raise_exc:
            raise RuntimeError("llm down")

        class _Resp:
            content = self.content
            usage = TokenUsage(model="fake", prompt_tokens=10, completion_tokens=5)

        return _Resp()


def _state(**overrides):  # noqa: ANN001, ANN202
    """构造最小状态。"""
    state = {
        "query": "清蒸鲈鱼怎么做？",
        "original_query": "清蒸鲈鱼怎么做？",
        "intent": IntentType.FACT,
        "plan": [],
        "reflect_feedback": None,
        "token_usage": [],
    }
    state.update(overrides)
    return state


class TestDirectAnswer:
    """chitchat 直答（E-02：零工具调用）。"""

    @pytest.mark.asyncio
    async def test_chitchat_single_direct_step_no_llm(self) -> None:
        updates = await planner_node(_state(intent=IntentType.CHITCHAT, query="你好"))
        plan = updates["plan"]
        assert len(plan) == 1
        assert plan[0].tool == "direct_answer"  # 零检索工具调用
        assert updates["current_step"] == 0

    @pytest.mark.asyncio
    async def test_chitchat_accepts_string_intent(self) -> None:
        updates = await planner_node(_state(intent="chitchat"))
        assert updates["plan"][0].tool == "direct_answer"


class TestIncrementalPlan:
    """回环增量补计划（followup_queries 注入）。"""

    @pytest.mark.asyncio
    async def test_followup_queries_appended(self) -> None:
        feedback = ReflectFeedback(
            sufficient=False,
            missing_aspects=["火候"],
            followup_queries=["清蒸鲈鱼的火候", "蒸制时间"],
        )
        state = _state(
            plan=[PlanStep(step_id="step-1", tool="dense", query="清蒸鲈鱼做法")],
            reflect_feedback=feedback,
        )
        updates = await planner_node(state)
        plan = updates["plan"]
        assert len(plan) == 3
        assert plan[1].query == "清蒸鲈鱼的火候"
        assert plan[2].query == "蒸制时间"
        assert updates["current_step"] == 1  # 从新增步开始
        assert updates["reflect_feedback"] is None  # 消费后清空

    @pytest.mark.asyncio
    async def test_followup_capped_at_two(self) -> None:
        feedback = ReflectFeedback(
            sufficient=False,
            followup_queries=["q1", "q2", "q3"],
        )
        state = _state(
            plan=[PlanStep(step_id="step-1", tool="dense", query="x")],
            reflect_feedback=feedback,
        )
        updates = await planner_node(state)
        assert len(updates["plan"]) == 3  # 1 既有 + 2 新增上限


class TestLLMPlanGeneration:
    """首轮 LLM JSON 计划生成。"""

    @pytest.mark.asyncio
    async def test_valid_json_plan_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeLLM(
            '{"steps": [{"tool": "dense", "query": "清蒸鲈鱼做法"},'
            ' {"tool": "graph", "query": "鲈鱼 食材关系"}]}'
        )
        monkeypatch.setattr("app.agent.nodes.planner._get_llm", lambda: fake)
        updates = await planner_node(_state())
        plan = updates["plan"]
        assert len(plan) == 2
        assert plan[0].tool == "dense"
        assert plan[1].tool == "graph"
        assert len(updates["token_usage"]) == 1  # 用量追加

    @pytest.mark.asyncio
    async def test_invalid_tools_filtered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeLLM(
            '{"steps": [{"tool": "hack", "query": "x"},'
            ' {"tool": "dense", "query": "清蒸鲈鱼"}]}'
        )
        monkeypatch.setattr("app.agent.nodes.planner._get_llm", lambda: fake)
        updates = await planner_node(_state())
        assert len(updates["plan"]) == 1
        assert updates["plan"][0].tool == "dense"

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = FakeLLM("", raise_exc=True)
        monkeypatch.setattr("app.agent.nodes.planner._get_llm", lambda: fake)
        updates = await planner_node(_state())
        assert len(updates["plan"]) == 1
        assert updates["plan"][0].tool == "dense"

    def test_parse_broken_json_falls_back(self) -> None:
        plan = _parse_plan("{broken json}", "清蒸鲈鱼")
        assert len(plan) == 1 and plan[0].tool == "dense"

    def test_parse_caps_steps_at_three(self) -> None:
        content = '{"steps": [' + ",".join(
            '{"tool": "dense", "query": "q%d"}' % i for i in range(5)
        ) + "]}"
        plan = _parse_plan(content, "q")
        assert len(plan) == 3
