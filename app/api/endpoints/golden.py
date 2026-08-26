"""
golden 回流端点（02 §3.11 · D8 · 单元 7.2）。

GET /admin/golden/export —— 点踩 bad case 清单 CSV 流（反馈队列
导出入口，admin 工具卡消费）。bad case 来源为点踩反馈记录；
持久化存储随 10.x Postgres 接线，当前为进程内登记队列。
"""

# --- 标准库 ---
import csv
import io
from datetime import datetime, timezone

# --- 第三方库 ---
from fastapi import APIRouter, Depends, Query
from app.api.security import require_admin
from fastapi.responses import StreamingResponse

router = APIRouter()

# 进程内 bad case 登记队列（10.x 迁移 Postgres 持久化）
_BAD_CASES: list[dict[str, str]] = []


def record_bad_case(session_id: str, message_id: str, query: str, answer: str) -> None:
    """登记一条点踩 bad case（反馈端点调用）。

    Args:
        session_id: 会话 ID。
        message_id: 被点踩消息 ID。
        query: 用户查询。
        answer: 被点踩答案。
    """
    _BAD_CASES.append(
        {
            "session_id": session_id,
            "message_id": message_id,
            "query": query,
            "answer": answer,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def _render_csv(since: str | None) -> str:
    """渲染 bad case CSV 文本。

    Args:
        since: ISO 时间过滤（仅导出该时间之后的记录）。

    Returns:
        CSV 文本（含列头）。
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["session_id", "message_id", "query", "answer", "created_at"])
    for case in _BAD_CASES:
        if since and case["created_at"] < since:
            continue
        writer.writerow(
            [
                case["session_id"],
                case["message_id"],
                case["query"],
                case["answer"],
                case["created_at"],
            ]
        )
    return buf.getvalue()


@router.get("/golden/export")
async def export_golden(
    since: str | None = Query(default=None, description="ISO 时间过滤"),
    user: dict[str, object] = Depends(require_admin),
) -> StreamingResponse:
    """导出点踩 bad case 清单（CSV 流，golden 回流）。

    Args:
        since: 仅导出该时间之后的记录（可选）。

    Returns:
        StreamingResponse: text/csv 流。
    """
    content = _render_csv(since)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=golden_bad_cases.csv"},
    )
