"""
LangGraph Agent 状态定义。

定义 Agent 工作记忆的 TypedDict 结构。
"""

# --- 标准库 ---
from typing import Annotated, Any, TypedDict

# --- 第三方库 ---
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

# --- 本地模块 ---
from app.retrieval.dense_retriever import RetrievalResult


class AgentState(TypedDict):
    """Agent 工作记忆状态。

    在 LangGraph 各节点间传递，记录完整的执行上下文。

    Attributes:
        messages: 对话消息列表（自动追加）。
        query: 用户原始查询。
        rewritten_query: 改写后的查询。
        entities: 提取的实体列表。
        retrieved_evidence: 检索到的证据列表。
        plan: 当前执行计划。
        current_step: 当前执行步骤。
        final_answer: 最终生成的答案。
        citations: 引用来源信息。
        token_usage: Token 使用统计。
        needs_more_retrieval: 是否需要更多检索。
        faithfulness_score: 忠实度评分。
        error: 错误信息。
    """

    messages: Annotated[list[BaseMessage], add_messages]
    query: str
    rewritten_query: str
    entities: list[dict[str, str]]
    retrieved_evidence: list[RetrievalResult]
    plan: str
    current_step: int
    final_answer: str
    citations: list[dict[str, Any]]
    token_usage: dict[str, int]
    needs_more_retrieval: bool
    faithfulness_score: float
    error: str | None
