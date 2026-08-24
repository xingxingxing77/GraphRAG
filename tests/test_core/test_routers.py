"""条件边路由真值表测试（单元 0.5/5.1 S3，07 §5）。

覆盖四路由：chitchat 直答 / A2 短路（预留）/ B4 预算耗尽 /
recursion 兜底（重试上限）。
"""

# --- 标准库 ---
from typing import Any

# --- 本地模块 ---
from app.agent.routers import (
    MAX_RETRIEVAL_ROUNDS,
    MAX_SELF_CORRECTION_RETRIES,
    _degrade,
    route_after_reflector,
    route_after_self_correction,
    route_after_tool_router,
    route_reflect_entry,
)
from app.core.models import PlanStep


def _state(**overrides: Any) -> dict[str, Any]:
    """构造满足 AgentState 必填键的最小状态。"""
    state: dict[str, Any] = {
        "query": "清蒸鲈鱼怎么做？",
        "original_query": "清蒸鲈鱼怎么做？",
        "plan": [PlanStep(step_id="step-1", tool="dense", query="清蒸鲈鱼做法")],
        "current_step": 0,
        "retrieval_rounds": 0,
        "needs_more_retrieval": False,
        "answer": "",
        "faithfulness_score": 1.0,
        "self_correction_retries": 0,
        "degraded": False,
        "token_budget_exhausted": False,
    }
    state.update(overrides)
    return state


class TestRouteAfterToolRouter:

    def test_direct_answer_goes_to_generator(self) -> None:
        state = _state(plan=[PlanStep(step_id="step-1", tool="direct_answer", query="你好")])
        assert route_after_tool_router(state) == "generator"

    def test_budget_exhausted_goes_to_generator(self) -> None:
        state = _state(token_budget_exhausted=True)
        assert route_after_tool_router(state) == "generator"

    def test_normal_plan_goes_to_reflector(self) -> None:
        assert route_after_tool_router(_state()) == "reflector"


class TestRouteAfterReflector:

    def test_loop_back_when_insufficient_and_under_round_cap(self) -> None:
        state = _state(needs_more_retrieval=True, retrieval_rounds=0)
        assert route_after_reflector(state) == "planner"

    def test_stop_at_round_cap(self) -> None:
        state = _state(needs_more_retrieval=True, retrieval_rounds=MAX_RETRIEVAL_ROUNDS)
        assert route_after_reflector(state) == "generator"

    def test_sufficient_goes_to_generator(self) -> None:
        state = _state(needs_more_retrieval=False)
        assert route_after_reflector(state) == "generator"

    def test_budget_exhausted_overrides_loop(self) -> None:
        state = _state(needs_more_retrieval=True, token_budget_exhausted=True)
        assert route_after_reflector(state) == "generator"


class TestRouteAfterSelfCorrection:

    def test_low_score_first_retry_regenerates(self) -> None:
        state = _state(faithfulness_score=0.3, self_correction_retries=0)
        assert route_after_self_correction(state) == "generator"

    def test_retry_exhausted_ends(self) -> None:
        state = _state(
            faithfulness_score=0.3,
            self_correction_retries=MAX_SELF_CORRECTION_RETRIES,
        )
        assert route_after_self_correction(state) == "__end__"

    def test_high_score_ends(self) -> None:
        state = _state(faithfulness_score=0.9)
        assert route_after_self_correction(state) == "__end__"


class TestReflectEntryShortCircuit:
    """A2 反思入口短路判定（05 §5.2：条件边函数内纯代码判定）。"""

    def test_normal_route_to_reflector(self) -> None:
        assert route_reflect_entry(_state()) == "reflector"

    def test_budget_exhausted_short_circuits_to_generator(self) -> None:
        state = _state(token_budget_exhausted=True)
        assert route_reflect_entry(state) == "generator"


class TestDegradeHelper:
    """_degrade 统一降级助手置位真值表（05 §5.3 / B4 / M3）。"""

    def test_sets_degraded_and_budget_flags(self) -> None:
        update = _degrade(_state(), reason="budget-exhausted")
        assert update["degraded"] is True
        assert update["token_budget_exhausted"] is True

    def test_idempotent_on_already_degraded_state(self) -> None:
        state = _state(degraded=True, token_budget_exhausted=True)
        update = _degrade(state, reason="llm-fallback")
        assert update == {
            "degraded": True,
            "token_budget_exhausted": True,
            "degraded_reasons": ["llm-fallback"],
        }

    def test_budget_exhausted_state_never_loops(self) -> None:
        """B4：预算耗尽态下全部条件边直入 generator，不回环。"""
        state = _state(
            token_budget_exhausted=True,
            needs_more_retrieval=True,
            faithfulness_score=0.0,
            self_correction_retries=0,
        )
        assert route_after_tool_router(state) == "generator"
        assert route_reflect_entry(state) == "generator"
        assert route_after_reflector(state) == "generator"
