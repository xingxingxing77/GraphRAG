"""
解析调试端点（02 §3.11，单元 1.2 关联）。

POST /admin/parsing/preview —— 上传样例文件或按 doc_id 预览解析结果
（限支持格式：md/html/pdf；展示解析文本与标题树）。
"""

# --- 标准库 ---
import hashlib
from datetime import datetime, timezone

# --- 第三方库 ---
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

# --- 本地模块 ---
from app.api.deps import get_ingestion_service
from app.api.errors import ErrorCode
from app.core.models import ParsingPreviewResponse, RawDocument
from app.pipeline.ingestion.loader import deterministic_doc_id
from app.pipeline.ingestion.service import IngestionService
from app.pipeline.parsing.router import FormatRouter

router = APIRouter()

_router = FormatRouter()


@router.post("/parsing/preview", response_model=ParsingPreviewResponse)
async def parsing_preview(
    doc_id: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    service: IngestionService = Depends(get_ingestion_service),
) -> ParsingPreviewResponse:
    """解析预览：multipart 上传样例文件，或按 doc_id 取最近采集文档。

    Args:
        doc_id: 已采集文档 ID（与 file 二选一）。
        file: 上传的样例文件（限 md/html/pdf）。
        service: 采集编排器（doc_id 查找用）。

    Returns:
        ParsingPreviewResponse: text + structure_tree + format_meta。

    Raises:
        HTTPException: 400 缺少输入或格式不支持。
    """
    # TODO: admin 鉴权 + SYS_403_DEBUG_DISABLED 生产开关（10.2/10.6）
    if file is not None and file.filename:
        raw_bytes = await file.read()
        raw_doc = RawDocument(
            doc_id=deterministic_doc_id(file.filename),
            source_path=file.filename,
            raw_bytes=raw_bytes,
            mime_type=file.content_type or "application/octet-stream",
            timestamp=datetime.now(timezone.utc),
            content_hash=hashlib.sha256(raw_bytes).hexdigest(),
        )
    elif doc_id:
        raw_doc = next(
            (d for d in service.last_documents if d.doc_id == doc_id), None
        )
        if raw_doc is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": ErrorCode.SYS_404_NOT_FOUND.value,
                    "message": f"doc_id 未在最近采集批次中: {doc_id}",
                },
            )
    else:
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.SYS_400_VALIDATION.value,
                "message": "需提供 doc_id 或上传 file",
            },
        )

    try:
        parsed = await _router.parse(raw_doc)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": ErrorCode.SYS_400_VALIDATION.value, "message": str(exc)},
        ) from exc
    return ParsingPreviewResponse(
        text=parsed.text,
        structure_tree=parsed.structure_tree,
        format_meta=parsed.format_meta,
    )
