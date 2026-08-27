"""
查询理解节点（架构 L2 · M2 · 单元 6.1/6.2）。

图内前置节点（START → query_understanding → planner）：
- chitchat 规则前置命中 → 零 LLM 直出（LangSmith 无本节点 span）；
- 否则 M2 合并式结构化调用（意图/改写/分解/实体一次产出）；
- D4 定档回写：auto 由意图矩阵定档（02 §5，架构 2.4），显式档位透传；
- 产出 rewritten_query 供 Planner/检索链路消费（改写在 load_memory
  注入之后，见 05 §5.5）。
"""

# --- 标准库 ---
import logging
from typing import Any

# --- 本地模块 ---
from app.agent.state import AgentState
from app.core.models import IntentType
from app.query.router import resolve_latency_tier, understand_query

logger = logging.getLogger(__name__)


async def query_understanding_node(state: AgentState) -> dict[str, Any]:
    """查询理解节点：M2 合并调用 + D4 定档回写。

    Args:
        state: 当前 Agent 状态（读取 original_query/latency_tier 入参）。

    Returns:
        状态增量：query（改写后）/ intent / latency_tier（具体档位）。
    """
    raw_query = state.get("query") or state.get("original_query", "")
    query = raw_query.strip()
    requested_tier = str(state.get("latency_tier") or "auto")

    # 空输入守卫：空白查询直接按 chitchat/fast 短路，避免进入 LLM 导致无意义错误冒泡为 500
    if not query:
        logger.info("query_understanding 空输入守卫命中（fast/chitchat 短路）")
        return {
            "query": "",
            "intent": IntentType.CHITCHAT,
            "latency_tier": resolve_latency_tier(IntentType.CHITCHAT, requested_tier),
        }

    # query 已含 load_memory 注入上下文（注入在改写前，04 §4/J17）
    result = await understand_query(query)
    tier = resolve_latency_tier(result.intent, requested_tier)

    updates: dict[str, Any] = {
        "query": result.rewritten_query or query,
        "intent": result.intent,
        "latency_tier": tier,
    }
    if result.rule_short_circuit:
        logger.info("query_understanding 规则短路命中（零 LLM 调用）")
    return updates
