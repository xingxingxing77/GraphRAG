"""
反馈端点（02 §3.5）。

POST /feedback —— 点赞/点踩上报，在线评估闭环数据源（架构第九章）。
rating=down 的记录自动进入 bad case 回流队列（D8 来源③）。
"""

# --- 第三方库 ---
from fastapi import APIRouter

# --- 本地模块 ---
from app.core.models import FeedbackRequest, FeedbackResponse

router = APIRouter()


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """上报点赞/点踩。

    Args:
        request: 反馈请求（rating ∈ up|down；reason 仅 down 必填）。

    Returns:
        FeedbackResponse: 受理结果。

    Raises:
        HTTPException: FEEDBACK_404_MESSAGE_NOT_FOUND。
    """
    # TODO: JWT 鉴权依赖注入
    # TODO: 落库反馈队列；rating=down 进 bad case 回流队列
    raise NotImplementedError
