"""
反思节点（架构 L6 · A2/C8 · 单元 5.4）。

职责：
- 评估证据充分性，输出结构化 ReflectFeedback（C8 契约）；
- sufficient=false 且回环未超限时驱动回环补检索（needs_more_retrieval）；
- 解析失败重试 1 次，仍失败安全置 sufficient=True（不无限回环，D5）。
A2 短路判定在条件边（routers.route_reflect_entry）前置执行，
短路时本节点不被调用（LangSmith trace 无 reflector span）。
"""

# --- 标准库 ---
import json
import logging
from typing import Any

# --- 本地模块 ---
from app.agent.state import AgentState
from app.core.models import ReflectFeedback

logger = logging.getLogger(__name__)

# 证据摘要条数上限（送评上限，控 prompt 体积）
_MAX_EVIDENCE_FOR_REVIEW = 5

_REFLECTOR_SYSTEM_PROMPT = """你是 GraphRAG 系统的证据评估器。判断给定证据是否足以回答用户问题，仅输出 JSON。
输出格式：{"sufficient": true|false, "missing_aspects": ["..."], "followup_queries": ["..."]}
规则：
- sufficient=true 时 missing_aspects 与 followup_queries 为空数组；
- sufficient=false 时 followup_queries 最多 2 条，针对缺失维度；
- 证据为空或完全无关时 sufficient=false；不要输出任何解释文字。"""


def _get_llm() -> Any:
    """获取 reflector 用 LLM 客户端（judge 角色，测试可替换）。

    Returns:
        LLMClient: 绑定角色条目的客户端。
    """
    from app.llm.registry import get_registry

    return get_registry().for_role("judge")


def _parse_feedback(content: str) -> ReflectFeedback | None:
    """解析 LLM JSON 输出为 ReflectFeedback。

    Args:
        content: LLM 输出文本（期望 JSON）。

    Returns:
        ReflectFeedback；解析失败返回 None。
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or "sufficient" not in data:
        return None
    try:
        return ReflectFeedback(
            sufficient=bool(data["sufficient"]),
            missing_aspects=[str(x) for x in (data.get("missing_aspects") or [])],
            followup_queries=[str(x) for x in (data.get("followup_queries") or [])][:2],
        )
    except Exception:  # noqa: BLE001 - 结构异常视为解析失败
        return None


def _build_evidence_digest(state: AgentState) -> str:
    """构造送评证据摘要（Top-N，控 prompt 体积）。

    Args:
        state: 当前 Agent 状态。

    Returns:
        编号列表形式的证据摘要文本。
    """
    evidence = (state.get("retrieved_evidence") or [])[:_MAX_EVIDENCE_FOR_REVIEW]
    lines = [
        f"[{i + 1}] ({r.source.value if hasattr(r.source, 'value') else r.source}) "
        f"{r.content[:200]}"
        for i, r in enumerate(evidence)
    ]
    return "\n".join(lines)


async def reflector_node(state: AgentState) -> dict[str, Any]:
    """反思节点：评估证据充分性并产出结构化反馈。

    Args:
        state: 当前 Agent 状态。

    Returns:
        状态增量：reflect_feedback / needs_more_retrieval。
    """
    query = state.get("query") or state.get("original_query", "")
    evidence = state.get("retrieved_evidence") or []

    # 无证据可评：直接进入生成（不做无意义回环）
    if not evidence:
        early = ReflectFeedback(sufficient=True)
        return {"reflect_feedback": early, "needs_more_retrieval": False}

    digest = _build_evidence_digest(state)
    user_prompt = f"用户问题：{query}\n\n候选证据：\n{digest}"

    # LLM 结构化评估（解析失败重试 1 次）
    feedback: ReflectFeedback | None = None
    for attempt in range(2):
        try:
            llm = _get_llm()
            resp = await llm.chat(
                [
                    {"role": "system", "content": _REFLECTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            feedback = _parse_feedback(resp.content)
        except Exception as exc:  # noqa: BLE001 - LLM 失败进入重试/兜底
            logger.warning("reflector LLM 调用失败(第%d次): %s", attempt + 1, exc)
            feedback = None
        if feedback is not None:
            break

    if feedback is None:
        # 重试耗尽：安全兜底 sufficient=True（不无限回环，D5）
        logger.warning("reflector 输出解析失败重试耗尽，兜底 sufficient=True")
        feedback = ReflectFeedback(sufficient=True)

    return {
        "reflect_feedback": feedback,
        "needs_more_retrieval": not feedback.sufficient,
    }
