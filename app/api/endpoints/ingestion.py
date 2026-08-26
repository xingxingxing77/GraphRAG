"""
采集调试端点（02 §3.11，单元 1.1 关联）。

POST /admin/ingestion/run —— 触发采集扫描（全量/增量）
GET  /admin/ingestion/scans —— 扫描结果列表

统一约定同 §3.10：JWT + role=admin（鉴权依赖随 10.2 接入），写审计日志。
"""

# --- 第三方库 ---
from fastapi import APIRouter, Depends
from app.api.security import require_admin

# --- 本地模块 ---
from app.api.deps import get_ingestion_service
from app.core.models import IngestionRunRequest, Paged, ScanRecord, TaskAccepted
from app.pipeline.ingestion.service import IngestionService

router = APIRouter()


@router.post("/ingestion/run", status_code=202, response_model=TaskAccepted)
async def run_ingestion(
    request: IngestionRunRequest = IngestionRunRequest(),
    service: IngestionService = Depends(get_ingestion_service),
    user: dict[str, object] = Depends(require_admin),
) -> TaskAccepted:
    """触发采集扫描（full | incremental）。

    骨架阶段同步执行并返回扫描任务 ID；异步任务化随 admin
    任务体系（10.6 TaskProgressPanel）完善。

    Args:
        request: 扫描模式与可选 source。
        service: 采集编排器。

    Returns:
        TaskAccepted: task_id = 本次 scan_id。
    """
    record = await service.run(mode=request.mode)
    return TaskAccepted(task_id=record.scan_id)


@router.get("/ingestion/scans", response_model=Paged[ScanRecord])
async def list_scans(
    cursor: str | None = None,
    limit: int = 20,
    service: IngestionService = Depends(get_ingestion_service),
    user: dict[str, object] = Depends(require_admin),
) -> Paged[ScanRecord]:
    """扫描结果列表（新→旧，骨架阶段内存分页）。

    Args:
        cursor: 分页游标（扫描记录偏移）。
        limit: 每页数量。

    Returns:
        Paged[ScanRecord]: discovered/changed/deduped 变更计数。
    """
    log = service.scan_log()
    start = int(cursor) if cursor else 0
    page = log[start : start + limit]
    next_cursor = str(start + limit) if start + limit < len(log) else None
    return Paged[ScanRecord](items=page, next_cursor=next_cursor)
