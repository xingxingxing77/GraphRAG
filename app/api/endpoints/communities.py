"""
社区摘要浏览端点（02 §3.11，单元 2.6 关联）。

GET /admin/communities —— 社区摘要只读浏览（level 过滤，游标分页）。
"""

# --- 第三方库 ---
from fastapi import APIRouter, Depends, Query
from app.api.security import require_admin
from neo4j.exceptions import Neo4jError, ServiceUnavailable

# --- 本地模块 ---
from app.api.deps import get_neo4j_client
from app.api.errors import ApiError, ErrorCode
from app.core.models import CommunitySummaryItem, Paged
from app.db.neo4j_client import Neo4jClient

router = APIRouter()


@router.get("/communities", response_model=Paged[CommunitySummaryItem])
async def list_communities(
    level: int | None = Query(default=None, description="层级过滤（缺省全部）"),
    cursor: str | None = Query(default=None, description="游标（偏移量）"),
    limit: int = Query(default=20, le=100),
    client: Neo4jClient = Depends(get_neo4j_client),
    user: dict[str, object] = Depends(require_admin),
) -> Paged[CommunitySummaryItem]:
    """社区摘要列表（新→旧，按 level/成员数排序）。

    Args:
        level: 层级过滤（0 叶子 / 1 父层；缺省全部）。
        cursor: 游标（偏移量字符串）。
        limit: 每页数量。
        client: Neo4j 客户端。

    Returns:
        Paged[CommunitySummaryItem]。

    Raises:
        ApiError: GRAPH_503_STORE_UNAVAILABLE（Neo4j 不可用）。
    """
    offset = int(cursor) if cursor else 0
    where = "WHERE m.level = $level" if level is not None else ""
    cypher = (
        f"MATCH (m:Community) {where} "
        "RETURN m.community_id AS cid, m.level AS level, "
        "       m.summary AS summary, m.member_count AS size "
        "ORDER BY level DESC, size DESC "
        "SKIP $skip LIMIT $limit"
    )
    params: dict[str, object] = {"skip": offset, "limit": limit + 1}
    if level is not None:
        params["level"] = level
    try:
        rows = await client.execute_cypher(cypher, params)
    except ServiceUnavailable as exc:
        raise ApiError(
            ErrorCode.GRAPH_503_STORE_UNAVAILABLE, "Neo4j 不可用（no-graph 降级中）"
        ) from exc
    except Neo4jError as exc:
        raise ApiError(
            ErrorCode.GRAPH_503_STORE_UNAVAILABLE, f"社区查询失败: {exc}"
        ) from exc

    has_more = len(rows) > limit
    items = [
        CommunitySummaryItem(
            community_id=str(r["cid"]),
            level=int(r["level"] or 0),
            summary=str(r["summary"] or ""),
            size=int(r["size"] or 0),
        )
        for r in rows[:limit]
    ]
    next_cursor = str(offset + limit) if has_more else None
    return Paged[CommunitySummaryItem](items=items, next_cursor=next_cursor)
