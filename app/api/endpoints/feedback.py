"""
反馈端点（02 §3.5 · 单元 10.2 · GAP-A1/GAP-A2）。

POST /feedback —— 点赞/点踩上报，在线评估闭环数据源（架构第九章）。
rating=down 的记录自动进入 bad case 回流队列（D8 来源③，golden 导出
消费）；query/answer 经 GAP-A1 的 thread_store 从 langgraph thread
checkpoint 反查真实快照（10.3 未竟项收口），依赖不可达时回退占位。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
from fastapi import APIRouter, Depends

# --- 本地模块 ---
from app.api import thread_store
from app.api.endpoints.golden import record_bad_case
from app.api.security import get_current_user
from app.core.models import FeedbackRequest, FeedbackResponse
from app.core.models import SessionMessage

router = APIRouter()


async def _resolve_snapshot(
    user_id: str, session_id: str, message_id: str
) -> tuple[str | None, str | None]:
    """反查被点踩消息的 (query, answer) 真实快照（GAP-A2）。

    按 message_id 在 thread 历史中定位被点踩的 assistant 消息，向前找最近
    的 user 消息作为 query；message_id 未精确命中（如 live 消息仍用前端
    本地 id）时回退到最近一次问答交换。thread 不存在/依赖不可达时返回
    (None, None)，由调用方回退占位。

    Args:
        user_id: 归属用户 ID。
        session_id: thread_id（session 锚点）。
        message_id: 被点踩消息 ID。

    Returns:
        (query, answer)；无法解析时二者为 None。
    """
    result = await thread_store.get_messages(user_id, session_id, None, 100)
    if result is None:
        return None, None
    messages: list[SessionMessage] = result[0]
    idx = next(
        (
            i
            for i, m in enumerate(messages)
            if m.message_id == message_id and m.role == "assistant"
        ),
        None,
    )
    if idx is None:
        # 未精确命中 → 最近一次 assistant
        assists = [i for i, m in enumerate(messages) if m.role == "assistant"]
        if not assists:
            return None, None
        idx = assists[-1]
    answer = messages[idx].content
    query = ""
    for j in range(idx - 1, -1, -1):
        if messages[j].role == "user":
            query = messages[j].content
            break
    return query or None, answer or None


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> FeedbackResponse:
    """上报点赞/点踩。

    rating=down 自动登记 bad case 回流队列；query/answer 经 thread
    checkpoint 反查真实快照（GAP-A2），反查失败回退占位串。

    Args:
        request: 反馈请求（rating ∈ up|down；reason 仅 down 必填）。
        user: JWT 用户声明。

    Returns:
        FeedbackResponse: 受理结果。
    """
    if request.rating == "down":
        query, answer = await _resolve_snapshot(
            user_id=str(user.get("sub", "")),
            session_id=request.session_id,
            message_id=request.message_id,
        )
        record_bad_case(
            session_id=request.session_id,
            message_id=request.message_id,
            query=query if query is not None else f"session:{request.session_id}",
            answer=answer if answer is not None else (request.comment or request.reason or "down"),
        )
    return FeedbackResponse(ok=True)
