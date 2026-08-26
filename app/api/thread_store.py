"""
会话存储（02 §3.2-§3.4 · GAP-A1 会话接线）。

权威源 = langgraph-server Threads API（J21 Postgres checkpoint），
thread_id 即 session 锚点。业务面（:8000）经 langgraph_sdk 代理
:8001 /threads：
- 列表：threads.search 按 metadata.user_id 过滤（updated_at 倒序，offset 游标）；
- 历史：threads.get_history 聚合各 checkpoint 的 original_query/answer
  → 用户/助手消息（含 citations/degraded/latency_tier/model）；
- 删除：threads.delete（先归属校验 metadata.user_id）。

可靠性（M3/D5）：langgraph-server 不可达时列表返回空、历史/删除
返回 None/False（404），不抛错阻塞主链路；调用方对我方始终优雅降级。
"""

# --- 标准库 ---
import logging
import time
from datetime import datetime, timezone
from typing import Any

# --- 第三方库 ---
import jwt as pyjwt
from langgraph_sdk import get_client

# --- 本地模块 ---
from app.core.config import get_settings
from app.core.models import SessionMessage, SessionSummary

logger = logging.getLogger(__name__)

# 标题截断长度（02 §3.2：首条用户消息 ≤30 字符）
_TITLE_MAX_CHARS = 30


def _service_token(user_id: str) -> str:
    """签发业务面 → langgraph-server 同源 JWT（J16/J19，共享 secret）。

    langgraph-server custom auth 校验同源 JWT；业务面以 sub=user_id
    的短时 service token 代理用户身份（不泄露客户端原 token）。
    """
    settings = get_settings()
    now = int(time.time())
    return pyjwt.encode(
        {"sub": user_id, "role": "user", "iat": now, "exp": now + 120},
        settings.jwt_secret,
        algorithm="HS256",
    )


def _client(user_id: str) -> Any:
    """构造 langgraph-server 异步客户端（携带该用户 service JWT）。"""
    settings = get_settings()
    return get_client(url=settings.langgraph_server_url, api_key=_service_token(user_id))


def _parse_dt(value: Any) -> datetime:
    """归一化时间戳为 datetime（datetime | ISO 字符串 | 缺省 now）。"""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


async def list_sessions(
    user_id: str, cursor: str | None, limit: int
) -> tuple[list[SessionSummary], str | None]:
    """列出用户会话（= langgraph threads，updated_at 倒序）。

    Args:
        user_id: 用户 ID（metadata.user_id 过滤）。
        cursor: offset 游标（整数字符串；缺省从 0 起）。
        limit: 每页条数。

    Returns:
        (会话摘要列表, 下一页游标)。
    """
    offset = int(cursor) if cursor and cursor.isdigit() else 0
    try:
        threads = await _client(user_id).threads.search(
            metadata={"user_id": user_id},
            limit=limit,
            offset=offset,
            sort_by="updated_at",
            sort_order="desc",
        )
    except Exception as exc:  # noqa: BLE001 - D5：依赖故障降级为空列表
        logger.warning("langgraph-server threads.search 失败（user=%s）: %s", user_id, exc)
        return [], None

    items: list[SessionSummary] = []
    for thread in threads:
        values = thread.get("values")
        title = "新会话"
        if isinstance(values, dict):
            query = values.get("original_query")
            if query:
                title = str(query)[:_TITLE_MAX_CHARS]
        items.append(
            SessionSummary(
                session_id=str(thread.get("thread_id", "")),
                title=title,
                message_count=0,
                created_at=_parse_dt(thread.get("created_at")),
                updated_at=_parse_dt(thread.get("updated_at")),
            )
        )
    next_cursor = str(offset + len(items)) if len(items) == limit else None
    return items, next_cursor


async def get_messages(
    user_id: str, session_id: str, cursor: str | None, limit: int
) -> tuple[list[SessionMessage], str | None] | None:
    """读取会话历史（thread 各 checkpoint 聚合 original_query/answer）。

    归属校验：thread metadata.user_id 与当前用户不符返回 None（404）。

    Args:
        user_id: 用户 ID。
        session_id: thread_id（session 锚点）。
        cursor: 预留消息游标（当前实现返回全量，next_cursor=None）。
        limit: 单次历史 checkpoint 数上限（get_history）。

    Returns:
        (消息列表, 下一页游标)；线程不存在/非本人/依赖故障返回 None。
    """
    try:
        client = _client(user_id)
        thread = await client.threads.get(session_id)
        metadata = thread.get("metadata") or {}
        if metadata.get("user_id") != user_id:
            return None
        history = await client.threads.get_history(thread_id=session_id, limit=limit)
    except Exception as exc:  # noqa: BLE001 - D5：依赖故障/线程不存在 → 404
        logger.warning("langgraph-server get_history 失败（thread=%s）: %s", session_id, exc)
        return None

    messages: list[SessionMessage] = []
    for state in history:
        values = state.get("values")
        if not isinstance(values, dict):
            continue
        checkpoint_id = str((state.get("checkpoint") or {}).get("checkpoint_id", ""))
        created_at = _parse_dt(state.get("created_at"))
        query = values.get("original_query")
        answer = values.get("answer")
        if query:
            messages.append(
                SessionMessage(
                    message_id=f"q_{checkpoint_id}",
                    role="user",
                    content=str(query),
                    created_at=created_at,
                )
            )
        if answer:
            messages.append(
                SessionMessage(
                    message_id=f"a_{checkpoint_id}",
                    role="assistant",
                    content=str(answer),
                    created_at=created_at,
                    citations=values.get("citations") or [],
                    degraded=bool(values.get("degraded")),
                    latency_tier=values.get("latency_tier"),
                    model=values.get("model"),
                )
            )
    return messages, None


async def delete_session(user_id: str, session_id: str) -> bool:
    """删除会话（= 删除 thread，先归属校验）。

    Args:
        user_id: 用户 ID。
        session_id: thread_id。

    Returns:
        True 删除成功；False 不存在/非本人/依赖故障。
    """
    try:
        client = _client(user_id)
        thread = await client.threads.get(session_id)
        metadata = thread.get("metadata") or {}
        if metadata.get("user_id") != user_id:
            return False
        await client.threads.delete(session_id)
        return True
    except Exception as exc:  # noqa: BLE001 - D5：依赖故障 → 404
        logger.warning("langgraph-server threads.delete 失败（thread=%s）: %s", session_id, exc)
        return False
