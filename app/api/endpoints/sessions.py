"""
会话端点（02 §3.2-§3.4 · 单元 10.2 · GAP-A1 会话接线）。

数据源：thread_store 经 langgraph-server Threads API（J21 Postgres
checkpoint，thread_id 即 session 锚点）；仅本人会话可见，他人会话
一律 404（防枚举）。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
from fastapi import APIRouter, Depends, Response

# --- 本地模块 ---
from app.api import thread_store
from app.api.errors import ApiError, ErrorCode
from app.api.security import get_current_user
from app.core.models import Paged, SessionMessage, SessionSummary

router = APIRouter()


@router.get("", response_model=Paged[SessionSummary])
async def list_sessions(
    cursor: str | None = None,
    limit: int = 20,
    user: dict[str, Any] = Depends(get_current_user),
) -> Paged[SessionSummary]:
    """当前用户会话列表（= langgraph threads，游标分页，仅本人）。

    标题为该线程最近原始查询截断（≤30 字符）。

    Args:
        cursor: 分页游标（offset）。
        limit: 每页数量。
        user: JWT 用户声明。

    Returns:
        Paged[SessionSummary]: 会话摘要列表。
    """
    items, next_cursor = await thread_store.list_sessions(
        user_id=str(user.get("sub", "")), cursor=cursor, limit=limit
    )
    return Paged[SessionSummary](items=items, next_cursor=next_cursor)


@router.get("/{session_id}/messages", response_model=Paged[SessionMessage])
async def get_session_messages(
    session_id: str,
    cursor: str | None = None,
    limit: int = 50,
    user: dict[str, Any] = Depends(get_current_user),
) -> Paged[SessionMessage]:
    """会话历史消息（thread checkpoint 聚合，归属校验，他人会话 404）。

    Args:
        session_id: thread_id（session 锚点）。
        cursor: 预留消息游标。
        limit: 历史 checkpoint 数上限（默认 50）。
        user: JWT 用户声明。

    Returns:
        Paged[SessionMessage]: 历史消息列表。

    Raises:
        ApiError: SESSION_404_NOT_FOUND（不存在/非本人/依赖故障）。
    """
    result = await thread_store.get_messages(
        user_id=str(user.get("sub", "")),
        session_id=session_id,
        cursor=cursor,
        limit=limit,
    )
    if result is None:
        raise ApiError(ErrorCode.SESSION_404_NOT_FOUND, "会话不存在或非本人")
    items, next_cursor = result
    return Paged[SessionMessage](items=items, next_cursor=next_cursor)


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    response: Response,
    user: dict[str, Any] = Depends(get_current_user),
) -> Response:
    """删除会话及其记忆（= 删除 thread，级联 checkpoint）。

    Args:
        session_id: thread_id。
        response: 响应对象（204 无内容）。
        user: JWT 用户声明。

    Returns:
        204 响应。

    Raises:
        ApiError: SESSION_404_NOT_FOUND。
    """
    deleted = await thread_store.delete_session(
        user_id=str(user.get("sub", "")), session_id=session_id
    )
    if not deleted:
        raise ApiError(ErrorCode.SESSION_404_NOT_FOUND, "会话不存在或非本人")
    response.status_code = 204
    return response
