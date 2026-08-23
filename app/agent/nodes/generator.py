"""
生成节点。

基于检索证据生成最终回答。
"""

# --- 标准库 ---
from typing import Any

# --- 本地模块 ---
from app.agent.state import AgentState


async def generator_node(state: AgentState) -> dict[str, Any]:
    """生成节点：基于证据生成答案。

    使用主 LLM 和检索到的证据生成最终回答，
    同时标注引用来源。

    Args:
        state: 当前 Agent 状态。

    Returns:
        更新后的状态字典片段（final_answer, citations, token_usage）。
    """
    # TODO: 构建 Prompt（系统指令 + 证据 + 用户查询）
    # TODO: 调用 LLM 生成答案
    # TODO: 提取引用标注并填充 citations
    # TODO: 统计 token_usage
    raise NotImplementedError
