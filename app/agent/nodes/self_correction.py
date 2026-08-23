"""
自校正节点。

检查生成内容与检索证据的一致性，检测幻觉。
"""

# --- 本地模块 ---
from app.agent.state import AgentState


async def self_correction_node(state: AgentState) -> dict:
    """自校正节点：验证生成内容的忠实度。

    检查生成的答案是否与检索证据一致，
    如果忠实度低于阈值，标记需要重新生成。

    Args:
        state: 当前 Agent 状态。

    Returns:
        更新后的状态字典片段（faithfulness_score, error）。
    """
    # TODO: 使用 LLM 或 NLI 模型评估答案与证据的一致性
    # TODO: 计算 faithfulness_score
    # TODO: 如果分数低于阈值，设置 error 信息
    # TODO: 条件路由：通过则 END，不通过则回到 generator
    raise NotImplementedError
