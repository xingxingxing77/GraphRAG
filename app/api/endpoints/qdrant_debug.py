"""
Qdrant 调试端点（02 §3.11，单元 3.1 关联）。

GET /admin/qdrant/points —— 按 doc_id 查 points（payload 查看）。
"""

# --- 第三方库 ---
from fastapi import APIRouter, Depends, Query
from app.api.security import ensure_debug_enabled, require_admin

# --- 本地模块 ---
from app.api.deps import get_qdrant_client
from app.core.models import QdrantPointItem, QdrantPointsResponse
from app.db.qdrant_client import QdrantDBClient

router = APIRouter()

# 业务集合前缀（04 §3.1 rag_{doc_type}）
_COLLECTION_PREFIX = "rag_"


@router.get("/qdrant/points", response_model=QdrantPointsResponse)
async def list_points(
    doc_id: str = Query(..., description="文档 ID"),
    limit: int = Query(default=100, le=500),
    client: QdrantDBClient = Depends(get_qdrant_client),
    user: dict[str, object] = Depends(require_admin),
) -> QdrantPointsResponse:
    """按 doc_id 查询全部业务集合中的 points。

    Args:
        doc_id: 文档 ID。
        limit: 每集合返回上限。
        client: Qdrant 客户端。

    Returns:
        QdrantPointsResponse: points 列表（含 payload）。
    """
    ensure_debug_enabled()
    points: list[QdrantPointItem] = []
    try:
        collections = await client.list_collections()
    except Exception:  # noqa: BLE001 - Qdrant 不可达返回空
        return QdrantPointsResponse(points=[])
    for name in collections:
        if not name.startswith(_COLLECTION_PREFIX):
            continue
        records = await client.scroll_by_doc(name, doc_id, limit=limit)
        points.extend(
            QdrantPointItem(
                id=str(r["id"]),
                chunk_id=str(r.get("chunk_id", "")),
                score=r.get("score"),
                payload=dict(r.get("payload") or {}),
            )
            for r in records
        )
    return QdrantPointsResponse(points=points)
