"""
聊天接口端点。

提供主聊天 API（POST /chat），支持 SSE 流式响应。
"""

# --- 标准库 ---
import json
from typing import AsyncGenerator

# --- 第三方库 ---
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

# --- 本地模块 ---
from app.api.models import ChatRequest, ChatResponse
from app.api.deps import get_agent, get_redis_client
from app.db.redis_client import RedisClient
from langgraph.graph.state import CompiledStateGraph

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    agent: CompiledStateGraph = Depends(get_agent),
    redis: RedisClient = Depends(get_redis_client),
) -> ChatResponse | StreamingResponse:
    """主聊天接口。

    接收用户查询，通过 LangGraph Agent 处理后返回答案。
    支持 SSE 流式响应，实时推送 Agent 思考步骤和最终答案。

    Args:
        request: 聊天请求。
        agent: LangGraph Agent 实例。
        redis: Redis 客户端。

    Returns:
        ChatResponse（非流式）或 StreamingResponse（流式 SSE）。
    """
    # TODO: 检查语义缓存（L1 缓存命中则直接返回）
    # TODO: 构建 Agent 输入 state
    # TODO: 如果 stream=True，返回 SSE StreamingResponse
    # TODO: 如果 stream=False，同步执行并返回 ChatResponse
    # TODO: 将结果写入语义缓存
    raise NotImplementedError


async def _stream_agent_response(
    agent: CompiledStateGraph,
    input_state: dict,
) -> AsyncGenerator[str, None]:
    """流式生成 Agent 响应的 SSE 事件。

    将 Agent 的每个节点执行步骤和最终答案以 SSE 格式推送。

    Args:
        agent: LangGraph Agent 实例。
        input_state: Agent 输入状态。

    Yields:
        SSE 格式的 JSON 字符串。
    """
    # TODO: 使用 agent.astream() 逐步执行
    # TODO: 将每个节点的输出格式化为 SSE event
    # TODO: 最终答案格式化为 {"event": "answer", "data": {...}}
    raise NotImplementedError
