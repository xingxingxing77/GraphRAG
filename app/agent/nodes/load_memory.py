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
from typing import Any

# --- 本地模块 ---
from app.agent.state import AgentState
from app.api.deps import get_memory_stack

logger = logging.getLogger(__name__)

# 顶层已导入，避免首个 async 节点内惰性导入触发 zoneinfo/sysconfig 的 os.getcwd 阻塞


async def _load_context(state: AgentState) -> str:
    """调用调度器组装上下文文本（异常返回空串）。"""

    stack = await get_memory_stack()
    ctx = await stack.scheduler.build_context(
        user_id=str(state.get("user_id", "")),
        session_id=str(state.get("session_id", "")),
        current_query=str(state.get("query", "")),
    )
    return ctx.context_text


async def load_memory_node(state: AgentState) -> dict[str, Any]:
    """注入工作记忆与相关情景（置于改写前，07 E-05 trace 断言点）。

    遗留锚点（10.4 F4 SSE 联调收口）：03 §3.4 updates 样例要求本节点
    帧载荷含计数字段 {injected_working_turns, episodic_hits,
    dedup_removed}；当前 AgentState 无对应契约字段，仅返回注入后
    query。补齐需加字段并与架构 §3.4 字段表 + routers 真值表同 PR。

    Args:
        state: 当前 Agent 状态。

    Returns:
        状态增量 {"query": 注入后查询}；无记忆或异常时返回空增量。
    """
    # P0-04: 新 run 起点清理研究缓存（幂等，多次调用安全）
    try:
        from app.agent.research_subgraph import clear_round_cache

        clear_round_cache()
    except Exception:
        pass
    try:
        context_text = await _load_context(state)
    except Exception as exc:  # noqa: BLE001 - D5：记忆故障不阻塞主链路
        logger.warning("load_memory 注入失败，原样放行: %s", exc)
        # E-09：记忆层故障 → no-memory 降级原因上报（9.1）
        return {"degraded_reasons": ["no-memory"]}
    if not context_text:
        return {}
    return {"query": f"{context_text}\n\n{state.get('query', '')}"}
