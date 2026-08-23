"""
LangGraph Agent 状态定义（架构 §3.4 字段表）。

AgentState 为 Agent 工作记忆的 TypedDict 结构，在各节点间传递。
带 ★ 注释的字段是条件边路由函数（app/agent/routers.py）的依赖项，
变更须同步架构文档 §3.4 与 routers 真值表（05 §3.1 契约先行）。
"""

# --- 标准库 ---
from typing import Annotated, Literal, TypedDict

# --- 第三方库 ---
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

# --- 本地模块 ---
from app.core.models import (
    Citation,
    IntentType,
    PlanStep,
    ReflectFeedback,
    RetrievalResult,
    TokenUsage,
)


class AgentState(TypedDict):
    """Agent 工作记忆状态（架构 §3.4 字段表落地）。

    run 入参经 02 §4 ChatRunInput 注入（original_query/session_id/user_id）；
    messages 通道承载 messages-tuple 流式事件（02 §4 streamMode）。

    Attributes:
        messages: 消息流通道（messages-tuple 流式事件载体，自动追加）。
        query: 当前查询（改写后）。
        original_query: 用户原始查询。
        session_id: 会话 ID（02 §4 run 入参）。
        user_id: 用户 ID（02 §4 run 入参）。
        intent: 意图（fast 路径判定依据，M2 产出）。
        latency_tier: 延迟档位（D4 三档）。
        plan: 检索计划（PlanStep 列表）。
        current_step: 当前执行步骤。
        retrieved_evidence: 累积证据。
        retrieval_rounds: ★ Reflector 回环计数（上限 3，05 §5.3）。
        needs_more_retrieval: ★ Reflector 路由开关。
        answer: 生成的答案草稿。
        faithfulness_score: ★ 自校正路由依据。
        self_correction_retries: ★ 重生成计数（上限 1）。
        citations: 引用列表。
        token_usage: 全程用量（每次 LLM 调用追加）。
        degraded: 是否降级运行（透传至 values 与 X-Degraded）。
        token_budget_exhausted: ★ B4 预算感知调度开关——wall-clock/token
            任一预算耗尽即置位，路由直入 Generator 降级作答。
        tool_call_cache: E3 run 内工具调用记忆化缓存，key 为
            (tool, query) 规范 hash，防止重复检索。
        reflect_feedback: Reflector 结构化输出，回环时 Planner
            增量补计划的依据。
    """

    messages: Annotated[list[BaseMessage], add_messages]
    query: str
    original_query: str
    session_id: str
    user_id: str
    intent: IntentType
    latency_tier: Literal["fast", "standard", "deep"]
    plan: list[PlanStep]
    current_step: int
    retrieved_evidence: list[RetrievalResult]
    retrieval_rounds: int  # ★
    needs_more_retrieval: bool  # ★
    answer: str
    faithfulness_score: float  # ★
    self_correction_retries: int  # ★
    citations: list[Citation]
    token_usage: list[TokenUsage]
    degraded: bool
    token_budget_exhausted: bool  # ★
    tool_call_cache: dict[str, RetrievalResult]
    reflect_feedback: ReflectFeedback | None
