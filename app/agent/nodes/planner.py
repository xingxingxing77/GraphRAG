"""
规划节点（架构 L6 · J9 · 单元 5.2）。

职责：
- chitchat「直答」单步（tool="direct_answer"，ToolRouter 零执行）；
- 回环时依据 reflect_feedback.followup_queries 增量补计划；
- 首轮经 LLM（query_understanding 角色，JSON mode）生成检索计划，
  解析失败/调用失败回退单步 dense 计划（不阻断主链路，D5）。
"""

# --- 标准库 ---
import json
import logging
from typing import Any

# --- 本地模块 ---
from app.agent.state import AgentState
from app.core.models import IntentType, PlanStep

logger = logging.getLogger(__name__)

# 计划步骤可用工具白名单（六路检索源）
_ALLOWED_TOOLS = {"dense", "sparse", "graph", "global", "fulltext", "web"}

# 单轮计划最大步数
_MAX_PLAN_STEPS = 3

_PLANNER_SYSTEM_PROMPT = """你是 GraphRAG 系统的检索规划器。根据用户问题制定检索计划，仅输出 JSON。
可用工具：
- dense：语义向量检索（默认首选）
- sparse：关键词精确匹配
- graph：实体关系结构化检索
- global：全局主题/社区摘要总结
- fulltext：全文关键词检索
- web：外部网络搜索（仅知识库明显不足时）
输出格式：{"steps": [{"tool": "<工具名>", "query": "<该步检索查询>"}]}
规则：steps 最多 3 步；每步 query 具体可执行；总结型问题用 global；不要输出任何解释文字。"""


def _get_llm() -> Any:
    """获取 planner 用 LLM 客户端（query_understanding 角色，测试可替换）。

    Returns:
        LLMClient: 绑定角色条目的客户端。
    """
    from app.llm.registry import get_registry

    return get_registry().for_role("query_understanding")


def _direct_answer_plan(query: str) -> list[PlanStep]:
    """构造 chitchat 直答单步计划（J9）。

    Args:
        query: 用户查询。

    Returns:
        仅含 direct_answer 的单步计划。
    """
    return [PlanStep(step_id="step-1", tool="direct_answer", query=query)]


def _fallback_plan(query: str) -> list[PlanStep]:
    """LLM 不可用时的回退计划（单步 dense，不阻断主链路）。

    Args:
        query: 用户查询。

    Returns:
        单步 dense 检索计划。
    """
    return [PlanStep(step_id="step-1", tool="dense", query=query)]


def _parse_plan(content: str, query: str) -> list[PlanStep]:
    """解析 LLM JSON 计划为 PlanStep 列表（非法条目剔除）。

    Args:
        content: LLM 输出文本（期望 JSON）。
        query: 原始查询（回退用）。

    Returns:
        PlanStep 列表；解析失败返回回退计划。
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        logger.warning("planner 输出解析失败，回退单步 dense 计划")
        return _fallback_plan(query)
    raw_steps = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(raw_steps, list) or not raw_steps:
        return _fallback_plan(query)
    steps: list[PlanStep] = []
    for i, item in enumerate(raw_steps[:_MAX_PLAN_STEPS]):
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool") or "")
        step_query = str(item.get("query") or "").strip()
        if tool not in _ALLOWED_TOOLS or not step_query:
            continue
        steps.append(
            PlanStep(step_id=f"step-{len(steps) + 1}", tool=tool, query=step_query)
        )
    return steps or _fallback_plan(query)


async def planner_node(state: AgentState) -> dict[str, Any]:
    """规划节点：制定/增量补充检索计划。

    Args:
        state: 当前 Agent 状态。

    Returns:
        状态增量：plan / current_step（回环时另清 reflect_feedback）。
    """
    intent = state.get("intent")
    intent_value = getattr(intent, "value", intent)
    query = state.get("query") or state.get("original_query", "")

    # chitchat「直答」单步（J9：零工具调用）
    if intent_value == IntentType.CHITCHAT.value:
        return {"plan": _direct_answer_plan(query), "current_step": 0}

    # 回环增量补计划（reflect_feedback.followup_queries 注入）
    feedback = state.get("reflect_feedback")
    existing_plan = state.get("plan") or []
    if feedback is not None and feedback.followup_queries and existing_plan:
        new_steps = [
            PlanStep(
                step_id=f"step-{len(existing_plan) + i + 1}",
                tool="dense",
                query=fq,
            )
            for i, fq in enumerate(feedback.followup_queries[:2])
        ]
        return {
            "plan": existing_plan + new_steps,
            "current_step": len(existing_plan),
            "reflect_feedback": None,
        }

    # 首轮：LLM JSON 计划生成（失败回退单步 dense）
    updates: dict[str, Any] = {"current_step": 0}
    try:
        llm = _get_llm()
        resp = await llm.chat(
            [
                {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            response_format={"type": "json_object"},
        )
        updates["plan"] = _parse_plan(resp.content, query)
        if resp.usage is not None:
            updates["token_usage"] = list(state.get("token_usage") or []) + [resp.usage]
    except Exception as exc:  # noqa: BLE001 - LLM 不可用回退，不阻断主链路
        logger.warning("planner LLM 调用失败，回退单步 dense 计划: %s", exc)
        updates["plan"] = _fallback_plan(query)
    return updates
