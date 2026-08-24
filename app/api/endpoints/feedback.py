"""
反馈端点（02 §3.5 · 单元 10.2）。

POST /feedback —— 点赞/点踩上报，在线评估闭环数据源（架构第九章）。
rating=down 的记录自动进入 bad case 回流队列（D8 来源③，golden 导出消费）。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
from fastapi import APIRouter, Depends

# --- 本地模块 ---
from app.api.endpoints.golden import record_bad_case
from app.api.security import get_current_user
from app.core.models import FeedbackRequest, FeedbackResponse

router = APIRouter()


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> FeedbackResponse:
    """上报点赞/点踩。

    rating=down 自动登记 bad case 回流队列（query/answer 占位取自
    message_id 关联，完整答案快照随 10.3 会话存储接线补齐）。

    Args:
        request: 反馈请求（rating ∈ up|down；reason 仅 down 必填）。
        user: JWT 用户声明。

    Returns:
        FeedbackResponse: 受理结果。
    """
    if request.rating == "down":
        record_bad_case(
            session_id=request.session_id,
            message_id=request.message_id,
            query=f"session:{request.session_id}",
            answer=request.comment or request.reason or "down",
        )
    return FeedbackResponse(ok=True)
