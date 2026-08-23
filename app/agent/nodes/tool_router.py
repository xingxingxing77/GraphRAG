"""
工具路由节点。

根据执行计划选择并调用合适的工具。
"""

# --- 标准库 ---
from typing import Any

# --- 本地模块 ---
from app.agent.state import AgentState


async def tool_router_node(state: AgentState) -> dict[str, Any]:
    """工具路由节点：根据计划选择工具并执行。

    根据当前计划步骤，决定调用哪个检索工具
    （向量检索、图谱检索、Web 搜索等），并执行。

    Args:
        state: 当前 Agent 状态。

    Returns:
        更新后的状态字典片段（retrieved_evidence 等）。
    """
    # TODO: 解析 plan 中的当前步骤
    # TODO: 选择对应的工具（search_vector_store / search_knowledge_graph / search_web）
    # TODO: 执行工具调用并将结果追加到 retrieved_evidence
    raise NotImplementedError
