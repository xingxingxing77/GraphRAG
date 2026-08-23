"""
检索研究子图（B5 子图化，单元 5.7）。

将「检索 → 融合 → 精排」封装为 ToolRouter 可调用的独立子图单元：
- 整轮调用结果经 tool_call_cache（E3）复用，避免重复检索
- LangSmith 中子图 span 天然分层（05 §7）
- interrupt() HITL 挂点预留（E2，开关 agent.hitl.enabled 默认 false）
"""

# --- 标准库 ---
from typing import Any

# --- 本地模块 ---
from app.agent.state import AgentState


async def research_subgraph(state: AgentState) -> dict[str, Any]:
    """执行一轮完整研究：检索 → 融合 → 精排。

    Args:
        state: 当前 Agent 状态（读取 query/plan/tool_call_cache）。

    Returns:
        状态增量更新：retrieved_evidence 合并去重、retrieval_rounds +1、
        tool_call_cache 写入本轮结果。
    """
    # TODO(5.7): 六路并行检索（asyncio.gather, return_exceptions=True）
    # TODO(5.7): RRF 融合 + Reranker 精排（L3-L5）
    # TODO(5.7): fan-in 合并去重后 retrieval_rounds += 1
    # TODO(5.7): evidence_pruner 在 checkpoint 写回前执行（B3）
    # TODO(5.7): interrupt() 挂点，受 agent.hitl.enabled 开关控制（E2）
    raise NotImplementedError
