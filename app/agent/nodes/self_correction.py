"""
自校正节点（架构 L8 · M3/B4 · 单元 5.6）。

职责：
- 忠实度校验：judge 角色 LLM 对答案与证据打分（faithfulness_score ★）；
- 分数低于阈值时注入失败原因供 Generator 重生成（重试上限 1，M3）；
- 校验 LLM 不可用时放行（score=1.0，不阻塞交付，D5）；
- 入口预算预检：token_budget_exhausted 已置位时跳过校验直放行
  （B4 路由层 _degrade 已接管降级作答）。
"""

# --- 标准库 ---
import json
import logging
from typing import Any

# --- 本地模块 ---
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

# 送评证据条数上限
_MAX_EVIDENCE_FOR_JUDGE = 5

_JUDGE_SYSTEM_PROMPT = """你是 GraphRAG 系统的忠实度评审员。评估「答案」对「参考资料」的忠实程度，仅输出 JSON。
输出格式：{"score": 0.0-1.0, "reason": "简要理由"}
评分标准：
- 1.0：答案全部事实均有资料支撑；
- 0.5-0.9：主体有支撑，少量细节无出处；
- <0.5：存在明显编造或与资料矛盾；
- 不要输出任何解释文字以外的内容。"""


def _get_llm() -> Any:
    """获取 judge 用 LLM 客户端（测试可替换）。

    Returns:
        LLMClient: 绑定 judge 角色的客户端。
    """
    from app.llm.registry import get_registry

    return get_registry().for_role("judge")


def _parse_score(content: str) -> float | None:
    """解析 judge JSON 输出为分数。

    Args:
        content: LLM 输出文本（期望 {"score": ...}）。

    Returns:
        分数（0-1）；解析失败返回 None。
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    raw_score = data.get("score")
    if raw_score is None:
        return None
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, score))


async def self_correction_node(state: AgentState) -> dict[str, Any]:
    """自校正节点：忠实度校验并驱动重生成决策。

    Args:
        state: 当前 Agent 状态。

    Returns:
        状态增量：faithfulness_score（校验失败/预算耗尽时放行 1.0）。
    """
    # B4：预算耗尽直放行（降级作答由 Generator 承担）
    if state.get("token_budget_exhausted"):
        return {"faithfulness_score": 1.0}

    answer = state.get("answer") or ""
    evidence = (state.get("retrieved_evidence") or [])[:_MAX_EVIDENCE_FOR_JUDGE]

    # 无答案或无证据可校验：放行
    if not answer or not evidence:
        return {"faithfulness_score": 1.0}

    evidence_block = "\n".join(
        f"[{i + 1}] {r.content[:200]}" for i, r in enumerate(evidence)
    )
    user_prompt = f"参考资料：\n{evidence_block}\n\n答案：{answer}"

    try:
        llm = _get_llm()
        resp = await llm.chat(
            [
                {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        score = _parse_score(resp.content)
    except Exception as exc:  # noqa: BLE001 - judge 不可用放行，不阻塞交付
        logger.warning("忠实度校验 LLM 失败，放行: %s", exc)
        score = None

    if score is None:
        # 解析/调用失败：放行（D5 不阻塞交付）
        return {"faithfulness_score": 1.0}

    # 重试计数由 Generator 重生成入口递增（路由保持纯函数）
    return {"faithfulness_score": score}
