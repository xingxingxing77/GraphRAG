"""
聊天业务面端点（02 §3.8）。

J19 双服务边界：聊天主链路（流式）在 langgraph-server :8001，
业务面仅承载 POST /chat/precheck —— L1 语义缓存短路查询（J22）。
"""

# --- 标准库 ---
import logging

# --- 第三方库 ---
from fastapi import APIRouter, Depends, Response

# --- 本地模块 ---
from app.api.deps import get_semantic_cache
from app.core.models import LatencyTier, PrecheckRequest, PrecheckResponse, SuggestedRun
from app.memory.semantic_cache import SemanticCache

logger = logging.getLogger(__name__)

router = APIRouter()

# 轻量启发式复杂度标记（02 §3.8：miss 时建议档位，可被前端覆盖）
_COMPLEX_MARKERS = ("对比", "区别", "为什么", "分析", "步骤", "原理")
_LONG_QUERY_CHARS = 60


def _suggest_tier(query: str) -> LatencyTier:
    """意图轻量启发式：长查询/多跳标记 → deep，其余 standard。"""
    if len(query) > _LONG_QUERY_CHARS or any(m in query for m in _COMPLEX_MARKERS):
        return LatencyTier.DEEP
    return LatencyTier.STANDARD


@router.post("/chat/precheck", response_model=PrecheckResponse)
async def chat_precheck(
    request: PrecheckRequest,
    response: Response,
    cache: SemanticCache = Depends(get_semantic_cache),
) -> PrecheckResponse:
    """L1 语义缓存短路查询（J22/H2，单元 8.3 S1）。

    查询向量 ANN 检索 Qdrant rag_cache，score >= 0.95 命中：
    - 命中返回 {hit:true, answer, citations, cache_score, matched_query}
    - 未命中返回 {hit:false, suggested_run}（意图启发式建议档位）

    缓存永不阻塞主链路：Qdrant/Embedding 异常时返回 {hit:false}
    并置 X-Degraded: no-cache，不报错（07 A-11）。

    Args:
        request: precheck 请求（query + session_id）。
        response: FastAPI 响应（用于置 X-Degraded 头）。
        cache: 语义缓存（依赖注入）。

    Returns:
        PrecheckResponse: 命中/未命中两态。
    """
    lookup = await cache.get_l1(request.query)
    if lookup.degraded:
        response.headers["X-Degraded"] = "no-cache"
    if lookup.hit:
        return PrecheckResponse(
            hit=True,
            answer=lookup.answer,
            citations=lookup.citations,
            cache_score=lookup.cache_score,
            matched_query=lookup.matched_query,
        )
    return PrecheckResponse(hit=False, suggested_run=SuggestedRun(latency_tier=_suggest_tier(request.query)))
