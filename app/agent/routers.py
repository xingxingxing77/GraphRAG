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
from pathlib import Path
from typing import Any

# --- 本地模块 ---
from app.agent.state import AgentState
from app.api.metrics import record_degraded

# --- M3 预算常量（config/reliability.yaml agent_budget 驱动，读取失败用默认） ---
_RELIABILITY_YAML = Path(__file__).resolve().parents[2] / "config" / "reliability.yaml"


def _load_budget() -> tuple[int, int, float]:
    """从 reliability.yaml 读取 M3 预算（回环上限/重试上限/忠实度阈）。

    Returns:
        (max_retrieval_rounds, max_self_correction_retries, faithfulness_threshold)。
    """
    try:
        import yaml

        with open(_RELIABILITY_YAML, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        budget = cfg.get("agent_budget") or {}
        return (
            int(budget.get("max_retrieval_rounds", 3)),
            int(budget.get("self_correction_max_retries", 1)),
            0.7,
        )
    except Exception:  # noqa: BLE001 - 配置缺失用默认
        return 3, 1, 0.7


MAX_RETRIEVAL_ROUNDS, MAX_SELF_CORRECTION_RETRIES, FAITHFULNESS_THRESHOLD = _load_budget()

# --- A2 短路参数（pipeline_config.yaml agent 段） ---
_PIPELINE_CONFIG_YAML = Path(__file__).resolve().parents[2] / "config" / "pipeline_config.yaml"


def _load_reflect_cfg() -> tuple[float, int]:
    """读取 A2 短路参数（Top-K 平均分阈 / 有效证据数下限）。

    Returns:
        (reflect_skip_threshold, evidence_enough_count)。
    """
    try:
        import yaml

        with open(_PIPELINE_CONFIG_YAML, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        agent_cfg = cfg.get("agent") or {}
        return (
            float(agent_cfg.get("reflect_skip_threshold", 0.7)),
            int(agent_cfg.get("evidence_enough_count", 5)),
        )
    except Exception:  # noqa: BLE001 - 配置缺失用默认
        return 0.7, 5


REFLECT_SKIP_THRESHOLD, EVIDENCE_ENOUGH_COUNT = _load_reflect_cfg()

# A2 均分评估的 Top-K 窗口
_A2_TOP_K = 5

# 图节点名常量（graph.py 注册同名节点）
NODE_QUERY_UNDERSTANDING = "query_understanding"
NODE_PLANNER = "planner"
NODE_TOOL_ROUTER = "tool_router"
NODE_REFLECTOR = "reflector"
NODE_GENERATOR = "generator"
NODE_SELF_CORRECTION = "self_correction"
# 单元 8.1/8.3：记忆注入前置节点（置于改写前）与写侧尾节点
NODE_LOAD_MEMORY = "load_memory"
NODE_WRITE_BACK = "write_back"


def _degrade(state: AgentState, reason: str) -> dict[str, Any]:
    """统一降级助手（05 §5.3）：所有超限路径共用。

    置 degraded + token_budget_exhausted 后路由直入 generator 降级作答，
    不抛错（M3/D5）。

    Args:
        state: 当前 Agent 状态。
        reason: 降级原因（上报 rag_degraded_total{reason} 指标）。

    Returns:
        状态增量更新字典（含 budget-exhausted 降级原因，9.1）。
    """
    record_degraded(reason)
    return {
        "degraded": True,
        "token_budget_exhausted": True,
        "degraded_reasons": [reason],
    }


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
    if state.get("token_budget_exhausted", False):
        return NODE_GENERATOR
    if _is_direct_answer_only(state):
        return NODE_GENERATOR
    return route_reflect_entry(state)


def route_reflect_entry(state: AgentState) -> str:
    """反思入口的 A2 短路判定（条件边函数内纯代码判定，05 §5.2）。

    短路条件（任一满足即跳过反思 LLM 调用）：
    1. B4 预算耗尽；
    2. fast 档（无需反思）；
    3. 有效证据数 ≥ evidence_enough_count；
    4. Top-K 平均分 ≥ reflect_skip_threshold。

    Args:
        state: 当前 Agent 状态。

    Returns:
        目标节点名：短路时 generator（trace 中无 reflector span），
        否则 reflector。
    """
    if state.get("token_budget_exhausted", False):
        return NODE_GENERATOR
    if state.get("latency_tier") == "fast":
        return NODE_GENERATOR
    evidence = state.get("retrieved_evidence") or []
    if len(evidence) >= EVIDENCE_ENOUGH_COUNT:
        return NODE_GENERATOR
    top = evidence[:_A2_TOP_K]
    if top:
        avg_score = sum(r.score for r in top) / len(top)
        if avg_score >= REFLECT_SKIP_THRESHOLD:
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
    if state.get("token_budget_exhausted", False):
        return NODE_GENERATOR
    if state.get("needs_more_retrieval", False) and state.get("retrieval_rounds", 0) < MAX_RETRIEVAL_ROUNDS:
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
        state.get("faithfulness_score", 1.0) < FAITHFULNESS_THRESHOLD
        and state.get("self_correction_retries", 0) < MAX_SELF_CORRECTION_RETRIES
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
    plan = state.get("plan") or []
    return len(plan) == 1 and plan[0].tool == "direct_answer"
