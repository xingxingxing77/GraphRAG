"""
会话存储（02 §3.2-§3.4 · 单元 10.2）。

开发期进程内会话登记（权威源迁移锚点：10.3 langgraph thread
checkpoint + Postgres，J21）。提供会话/消息的登记、分页查询、
归属校验与删除；业务面端点经本模块读写。
"""

# --- 标准库 ---
import uuid
from datetime import datetime, timezone
from typing import Any

# --- 本地模块 ---
from app.core.models import SessionMessage, SessionSummary

# 标题截断长度（02 §3.2：首条用户消息 ≤30 字符）
_TITLE_MAX_CHARS = 30


class SessionRecord:
    """单会话记录。

    Attributes:
        user_id: 归属用户。
        session_id: 会话 ID。
        messages: 消息列表（时间序）。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    def __init__(self, user_id: str, session_id: str) -> None:
        """初始化会话记录。

        Args:
            user_id: 归属用户 ID。
            session_id: 会话 ID。
        """
        now = datetime.now(timezone.utc)
        self.user_id = user_id
        self.session_id = session_id
        self.messages: list[SessionMessage] = []
        self.created_at = now
        self.updated_at = now

    @property
    def title(self) -> str:
        """会话标题（首条用户消息截断）。"""
        for msg in self.messages:
            if msg.role == "user":
                return msg.content[:_TITLE_MAX_CHARS]
        return "新会话"


# 进程内存储（10.3 迁移 Postgres checkpoint）
_STORE: dict[str, SessionRecord] = {}


def register_message(
    user_id: str,
    session_id: str,
    role: str,
    content: str,
    **extra: Any,
) -> SessionMessage:
    """登记一条消息（会话不存在时自动创建）。

    Args:
        user_id: 归属用户 ID。
        session_id: 会话 ID。
        role: user | assistant。
        content: 消息内容。
        **extra: 附加字段（citations/degraded/latency_tier/model）。

    Returns:
        登记后的 SessionMessage。
    """
    record = _STORE.get(session_id)
    if record is None or record.user_id != user_id:
        record = SessionRecord(user_id=user_id, session_id=session_id)
        _STORE[session_id] = record
    message = SessionMessage(
        message_id=f"m_{uuid.uuid4().hex[:12]}",
        role=role,  # type: ignore[arg-type]
        content=content,
        created_at=datetime.now(timezone.utc),
        **extra,
    )
    record.messages.append(message)
    record.updated_at = message.created_at
    return message


def list_sessions(
    user_id: str, cursor: str | None, limit: int
) -> tuple[list[SessionSummary], str | None]:
    """按归属列出会话（updated_at 倒序，游标分页）。

    Args:
        user_id: 用户 ID（仅本人会话）。
        cursor: 游标（上一页末条 session_id）。
        limit: 每页数量。

    Returns:
        (会话摘要列表, 下一页游标)。
    """
    records = sorted(
        (r for r in _STORE.values() if r.user_id == user_id),
        key=lambda r: r.updated_at,
        reverse=True,
    )
    start = 0
    if cursor:
        for i, r in enumerate(records):
            if r.session_id == cursor:
                start = i + 1
                break
    page = records[start : start + limit]
    items = [
        SessionSummary(
            session_id=r.session_id,
            title=r.title,
            message_count=len(r.messages),
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in page
    ]
    next_cursor = page[-1].session_id if len(page) == limit else None
    return items, next_cursor


def get_messages(
    user_id: str, session_id: str, cursor: str | None, limit: int
) -> tuple[list[SessionMessage], str | None] | None:
    """读取会话消息（归属校验）。

    Args:
        user_id: 用户 ID。
        session_id: 会话 ID。
        cursor: 游标（上一页末条 message_id）。
        limit: 每页数量。

    Returns:
        (消息列表, 下一页游标)；会话不存在或非本人返回 None。
    """
    record = _STORE.get(session_id)
    if record is None or record.user_id != user_id:
        return None
    messages = record.messages
    start = 0
    if cursor:
        for i, m in enumerate(messages):
            if m.message_id == cursor:
                start = i + 1
                break
    page = messages[start : start + limit]
    next_cursor = page[-1].message_id if len(page) == limit else None
    return page, next_cursor


def delete_session(user_id: str, session_id: str) -> bool:
    """删除会话（归属校验）。

    Args:
        user_id: 用户 ID。
        session_id: 会话 ID。

    Returns:
        True 删除成功；False 会话不存在或非本人。
    """
    record = _STORE.get(session_id)
    if record is None or record.user_id != user_id:
        return False
    del _STORE[session_id]
    return True


def clear_store() -> None:
    """清空存储（测试用）。"""
    _STORE.clear()
