"""
反思节点。

评估已有信息是否充分，决定是否需要继续检索。
"""

# --- 标准库 ---
from typing import Any

# --- 本地模块 ---
from app.agent.state import AgentState


async def reflector_node(state: AgentState) -> dict[str, Any]:
    """反思节点：评估检索结果的充分性。

    使用轻量 LLM（如 Qwen2.5-7B）判断当前已收集的证据
    是否足以回答用户问题。

    Args:
        state: 当前 Agent 状态。

    Returns:
        更新后的状态字典片段（needs_more_retrieval）。
    """
    # TODO: 使用 LLM 评估证据充分性
    # TODO: 设置 needs_more_retrieval = True/False
    # TODO: 如果不充分，更新 plan 添加新的检索步骤
    raise NotImplementedError
