"""
清洗调试端点（02 §3.11，单元 1.3 关联）。

POST /admin/cleaning/preview —— 清洗前后对比预览（diff 高亮被删片段）。
"""

# --- 第三方库 ---
from fastapi import APIRouter, Depends
from app.api.security import require_admin

# --- 本地模块 ---
from app.api.deps import get_ingestion_service
from app.api.errors import ApiError, ErrorCode
from app.core.models import CleaningPreviewRequest, CleaningPreviewResponse
from app.pipeline.cleaning.pipeline import build_cleaning_pipeline
from app.pipeline.ingestion.service import IngestionService
from app.pipeline.parsing.router import FormatRouter

router = APIRouter()

_format_router = FormatRouter()


def _removed_spans(before: str, after: str) -> list[str]:
    """按行 diff 提取被删除的片段（供前端高亮）。

    Args:
        before: 清洗前文本。
        after: 清洗后文本。

    Returns:
        被删除的非空行列表。
    """
    after_lines = set(after.splitlines())
    return [
        ln.strip()
        for ln in before.splitlines()
        if ln.strip() and ln not in after_lines
    ]


@router.post("/cleaning/preview", response_model=CleaningPreviewResponse)
async def cleaning_preview(
    request: CleaningPreviewRequest,
    service: IngestionService = Depends(get_ingestion_service),
    user: dict[str, object] = Depends(require_admin),
) -> CleaningPreviewResponse:
    """清洗前后对比预览。

    Args:
        request: doc_id + 可选 rules_override。
        service: 采集编排器（按 doc_id 取最近采集文档）。

    Returns:
        CleaningPreviewResponse: before/after/removed_spans/quality_score。

    Raises:
        ApiError: SYS_404_NOT_FOUND（doc_id 不在最近批次）。
    """
    raw_doc = next(
        (d for d in service.last_documents if d.doc_id == request.doc_id), None
    )
    if raw_doc is None:
        raise ApiError(
            ErrorCode.SYS_404_NOT_FOUND,
            f"doc_id 未在最近采集批次中: {request.doc_id}",
        )

    parsed = await _format_router.parse(raw_doc)
    pipeline = build_cleaning_pipeline()
    if request.rules_override is not None:
        allowed = set(request.rules_override)
        for rule in pipeline._rules:  # noqa: SLF001 - 预览场景按名过滤
            rule.enabled = rule.name in allowed

    cleaned = await pipeline.run(parsed)
    return CleaningPreviewResponse(
        before=parsed.text,
        after=cleaned.text,
        removed_spans=_removed_spans(parsed.text, cleaned.text),
        quality_score=cleaned.quality_score,
    )
