"""
条件边路由函数集中地（架构 §3.4 ★字段消费方，05 §5.3）。

所有条件边判定均为纯代码逻辑（A2 短路亦在此，05 §5.2），保证
LangSmith trace 中能看到"跳过"。真值表全覆盖单测见 07 §5
（chitchat 直答 / A2 短路 / B4 预算耗尽 / recursion 兜底四路由）。

路由阈值与上限来自 M3 预算表：
- retrieval_rounds 上限 3（05 §5.3）
- self_correction_retries 上限 1（架构 §3.4）
"""

# --- 标准库 ---
from typing import Any

# --- 本地模块 ---
from app.agent.state import AgentState

# --- M3 预算常量（TODO: 迁移至 config/reliability.yaml 并支持热更判定） ---
MAX_RETRIEVAL_ROUNDS = 3
MAX_SELF_CORRECTION_RETRIES = 1
FAITHFULNESS_THRESHOLD = 0.7

# 图节点名常量（graph.py 注册同名节点）
NODE_PLANNER = "planner"
NODE_TOOL_ROUTER = "tool_router"
NODE_REFLECTOR = "reflector"
NODE_GENERATOR = "generator"
NODE_SELF_CORRECTION = "self_correction"


def _degrade(state: AgentState, reason: str) -> dict[str, Any]:
    """统一降级助手（05 §5.3）：所有超限路径共用。

    置 degraded + token_budget_exhausted 后路由直入 generator 降级作答，
    不抛错（M3/D5）。

    Args:
        state: 当前 Agent 状态。
        reason: 降级原因（上报 rag_degraded_total{reason} 指标）。

    Returns:
        状态增量更新字典。
    """
    # TODO: 记录 Prometheus 指标 rag_degraded_total{reason}
    return {"degraded": True, "token_budget_exhausted": True}


def route_after_tool_router(state: AgentState) -> str:
    """tool_router 之后的条件边。

    路由优先级：
    1. B4 预算耗尽 → 直入 generator 降级作答
    2. chitchat「直答」单步（tool="direct_answer"，J9）→ 直入 generator
    3. 其余 → reflector（A2 短路判定见 route_reflect_entry）

    Args:
        state: 当前 Agent 状态。

    Returns:
        目标节点名。
    """
    if state["token_budget_exhausted"]:
        return NODE_GENERATOR
    if _is_direct_answer_only(state):
        return NODE_GENERATOR
    return NODE_REFLECTOR


def route_reflect_entry(state: AgentState) -> str:
    """反思入口的 A2 短路判定（条件边函数内纯代码判定，05 §5.2）。

    Args:
        state: 当前 Agent 状态。

    Returns:
        目标节点名：短路时 generator（trace 中无 reflector span），
        否则 reflector。
    """
    # TODO(5.4): A2 短路条件细化（fast 档/单步计划等短路规则）
    if state["token_budget_exhausted"]:
        return NODE_GENERATOR
    return NODE_REFLECTOR


def route_after_reflector(state: AgentState) -> str:
    """reflector 之后的条件边：回环补检索 or 进入生成。

    回环条件：needs_more_retrieval ★ 且 rounds < 3（增量补计划）；
    B4 预算耗尽时直入 generator 降级作答。

    Args:
        state: 当前 Agent 状态。

    Returns:
        目标节点名（planner / generator）。
    """
    if state["token_budget_exhausted"]:
        return NODE_GENERATOR
    if state["needs_more_retrieval"] and state["retrieval_rounds"] < MAX_RETRIEVAL_ROUNDS:
        return NODE_PLANNER
    return NODE_GENERATOR


def route_after_self_correction(state: AgentState) -> str:
    """self_correction 之后的条件边：重生成 or 结束。

    重生成条件：faithfulness_score ★ 低于阈值且 retries ★ < 1；
    重试耗尽后直接放行（degraded 标记在节点内置位）。

    Args:
        state: 当前 Agent 状态。

    Returns:
        目标节点名（generator / "__end__"）。
    """
    if (
        state["faithfulness_score"] < FAITHFULNESS_THRESHOLD
        and state["self_correction_retries"] < MAX_SELF_CORRECTION_RETRIES
    ):
        return NODE_GENERATOR
    return "__end__"


def _is_direct_answer_only(state: AgentState) -> bool:
    """判断计划是否为 chitchat 直答单步（J9）。

    Args:
        state: 当前 Agent 状态。

    Returns:
        True 表示计划仅含 direct_answer 步骤。
    """
    plan = state["plan"]
    return len(plan) == 1 and plan[0].tool == "direct_answer"
