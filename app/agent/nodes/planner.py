"""
规划节点。

分析用户查询，制定检索和推理计划。
"""

# --- 标准库 ---
from typing import Any

# --- 本地模块 ---
from app.agent.state import AgentState


async def planner_node(state: AgentState) -> dict[str, Any]:
    """规划节点：分析问题并制定执行计划。

    使用主 LLM（如 Qwen2.5-32B）分析用户查询，
    输出结构化的检索和推理步骤。

    Args:
        state: 当前 Agent 状态。

    Returns:
        更新后的状态字典片段（plan, current_step 等）。
    """
    # TODO: 使用 LLM 分析查询，生成执行计划
    # TODO: 更新 state["plan"] 和 state["current_step"]
    raise NotImplementedError
