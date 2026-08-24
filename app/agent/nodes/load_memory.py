"""
记忆注入前置节点（单元 8.1，架构 L9/J17，05 §5.4）。

置于查询改写之前（阶段 6 改写节点须排在本节点之后）：组装
工作记忆 + 情景记忆两段式上下文，拼接到当前查询前部供规划/
生成消费。original_query 保持不变（写侧尾节点与引用归因依据）。

可靠性：任何记忆层异常仅告警并原样放行（D5 降级不抛错，
记忆注入永不阻塞主链路）。
"""

# --- 标准库 ---
import logging

# --- 本地模块 ---
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


async def _load_context(state: AgentState) -> str:
    """调用调度器组装上下文文本（异常返回空串）。"""
    from app.api.deps import get_memory_stack

    stack = await get_memory_stack()
    ctx = await stack.scheduler.build_context(
        user_id=str(state.get("user_id", "")),
        session_id=str(state.get("session_id", "")),
        current_query=str(state.get("query", "")),
    )
    return ctx.context_text


async def load_memory_node(state: AgentState) -> dict[str, str]:
    """注入工作记忆与相关情景（置于改写前，07 E-05 trace 断言点）。

    Args:
        state: 当前 Agent 状态。

    Returns:
        状态增量 {"query": 注入后查询}；无记忆或异常时返回空增量。
    """
    try:
        context_text = await _load_context(state)
    except Exception as exc:  # noqa: BLE001 - D5：记忆故障不阻塞主链路
        logger.warning("load_memory 注入失败，原样放行: %s", exc)
        return {}
    if not context_text:
        return {}
    return {"query": f"{context_text}\n\n{state.get('query', '')}"}
