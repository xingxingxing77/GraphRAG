"""
分块调试端点（02 §3.11，单元 2.1 关联）。

POST /admin/chunking/preview —— 分块边界预览（chunk 边界高亮、
title_path 显示）。
"""

# --- 第三方库 ---
from fastapi import APIRouter, Depends

# --- 本地模块 ---
from app.api.deps import get_ingestion_service
from app.api.errors import ApiError, ErrorCode
from app.core.models import ChunkingPreviewRequest, ChunkingPreviewResponse
from app.pipeline.chunking.strategy import chunk_document
from app.pipeline.cleaning.pipeline import build_cleaning_pipeline
from app.pipeline.ingestion.service import IngestionService
from app.pipeline.parsing.router import FormatRouter

router = APIRouter()

_format_router = FormatRouter()


@router.post("/chunking/preview", response_model=ChunkingPreviewResponse)
async def chunking_preview(
    request: ChunkingPreviewRequest,
    service: IngestionService = Depends(get_ingestion_service),
) -> ChunkingPreviewResponse:
    """分块边界预览：按 doc_id 取最近采集文档，解析→清洗→分块。

    Args:
        request: doc_id。
        service: 采集编排器（按 doc_id 取最近采集文档）。

    Returns:
        ChunkingPreviewResponse: chunks（含 chunk_id/content/title_path/position）。

    Raises:
        ApiError: SYS_404_NOT_FOUND（doc_id 不在最近批次）。
    """
    # TODO: admin 鉴权 + SYS_403_DEBUG_DISABLED 生产开关（10.2/10.6）
    raw_doc = next(
        (d for d in service.last_documents if d.doc_id == request.doc_id), None
    )
    if raw_doc is None:
        raise ApiError(
            ErrorCode.SYS_404_NOT_FOUND,
            f"doc_id 未在最近采集批次中: {request.doc_id}",
        )

    parsed = await _format_router.parse(raw_doc)
    cleaned = await build_cleaning_pipeline().run(parsed)
    chunks = await chunk_document(cleaned)
    return ChunkingPreviewResponse(chunks=chunks)
