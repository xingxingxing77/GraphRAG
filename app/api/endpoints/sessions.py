"""
会话端点（02 §3.2-§3.4）。

数据源：thread checkpoint（Postgres，J21）聚合工作记忆窗口（Redis wm 键，04 §4）。
"""

# --- 第三方库 ---
from fastapi import APIRouter

# --- 本地模块 ---
from app.core.models import Paged, SessionMessage, SessionSummary

router = APIRouter()


@router.get("", response_model=Paged[SessionSummary])
async def list_sessions(
    cursor: str | None = None,
    limit: int = 20,
) -> Paged[SessionSummary]:
    """当前用户会话列表（游标分页）。

    title 为该会话首条用户消息截断（≤30 字符）。

    Args:
        cursor: 分页游标。
        limit: 每页数量。

    Returns:
        Paged[SessionSummary]: 会话摘要列表。
    """
    # TODO: JWT 鉴权依赖注入（仅本人会话）
    # TODO: 聚合 checkpoint 元数据 + wm 键
    raise NotImplementedError


@router.get("/{session_id}/messages", response_model=Paged[SessionMessage])
async def get_session_messages(
    session_id: str,
    cursor: str | None = None,
    limit: int = 50,
) -> Paged[SessionMessage]:
    """会话历史消息（聚合 thread checkpoint 与工作记忆）。

    Args:
        session_id: 会话 ID。
        cursor: 分页游标。
        limit: 每页数量（默认 50）。

    Returns:
        Paged[SessionMessage]: 历史消息列表。

    Raises:
        HTTPException: SESSION_404_NOT_FOUND（不存在或非本人，他人返回 404）。
    """
    # TODO: 校验会话归属（非本人 404）
    # TODO: 读取 thread checkpoint + wm 窗口合并
    raise NotImplementedError


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str) -> None:
    """删除会话及其记忆。

    行为：删除 thread checkpoint + 工作记忆 List + 该 session 的
    情景记忆 points（异步级联，A-05）。

    Args:
        session_id: 会话 ID。

    Raises:
        HTTPException: SESSION_404_NOT_FOUND。
    """
    # TODO: 校验会话归属
    # TODO: 级联清理 checkpoint / wm / episodic
    raise NotImplementedError
