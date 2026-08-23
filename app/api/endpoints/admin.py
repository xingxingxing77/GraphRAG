"""
管理接口端点组（02 §3.10）。

统一约定：鉴权 JWT 且 role=admin，否则 AUTH_403_FORBIDDEN；
全部写审计日志。调试与管道预览接口组（/admin/debug/*，02 §3.11）
随各关联单元落地，本骨架暂不含。
"""

# --- 第三方库 ---
from fastapi import APIRouter, Body

# --- 本地模块 ---
from app.core.models import (
    CacheClearRequest,
    CacheClearResponse,
    FeedbackResponse,
    HotReloadResponse,
    IndexRebuildRequest,
    Paged,
    ReviewDecisionRequest,
    ReviewQueueItem,
    TaskAccepted,
    TaskStatus,
)

router = APIRouter()


@router.post("/cache/clear", response_model=CacheClearResponse)
async def clear_cache(request: CacheClearRequest = Body(...)) -> CacheClearResponse:
    """按 scope/doc_id 清除缓存（失效联动）。

    Args:
        request: 清理范围与可选 doc_id。

    Returns:
        CacheClearResponse: 清除条目数。
    """
    # TODO: admin 鉴权 + 审计日志
    # TODO: 按 scope 清理 L1/L2 缓存；doc_id 反查失效联动
    raise NotImplementedError


@router.post("/index/rebuild", status_code=202, response_model=TaskAccepted)
async def rebuild_index(request: IndexRebuildRequest = Body(...)) -> TaskAccepted:
    """触发索引异步重建（vector/graph/fulltext/all）。

    Args:
        request: 重建范围与是否全量。

    Returns:
        TaskAccepted: 任务 ID（进度查 GET /admin/tasks/{task_id}）。

    Raises:
        HTTPException: ADMIN_409_TASK_RUNNING（已有重建任务执行中）。
    """
    # TODO: admin 鉴权 + 审计日志
    # TODO: 提交异步重建任务并返回 task_id
    raise NotImplementedError


@router.put("/config/hot-reload", response_model=HotReloadResponse)
async def hot_reload_config() -> HotReloadResponse:
    """J18 受限热更：清洗规则/检索权重/降级参数/agent.* 效率参数。

    写回 YAML + pydantic 重校验，无需重启；分块参数与 embedding
    模型禁止热更（01 §7）。操作自动落审计日志（操作人/时间/diff）。

    Returns:
        HotReloadResponse: 重载成功的配置与错误列表。
    """
    # TODO: admin 鉴权 + 审计日志
    # TODO: 重载可热更 YAML 并 pydantic 重校验
    raise NotImplementedError


@router.get("/review-queue", response_model=Paged[ReviewQueueItem])
async def list_review_queue(
    cursor: str | None = None,
    limit: int = 20,
) -> Paged[ReviewQueueItem]:
    """开放区实体人工审核队列（J12，按出现频次排序）。

    Args:
        cursor: 分页游标。
        limit: 每页数量。

    Returns:
        Paged[ReviewQueueItem]: 待审核实体列表。
    """
    # TODO: admin 鉴权
    # TODO: 查询 zone=open 实体按 freq 排序
    raise NotImplementedError


@router.post("/review/decision", response_model=FeedbackResponse)
async def review_decision(request: ReviewDecisionRequest) -> FeedbackResponse:
    """审核决定：approve 升级白名单并重放关联三元组；reject 拒绝。

    Args:
        request: 实体 ID + 决定。

    Returns:
        FeedbackResponse: {ok: true}。
    """
    # TODO: admin 鉴权 + 审计日志
    # TODO: approve → graph_schema 白名单升级 + 三元组重放（G4 幂等）
    raise NotImplementedError


@router.get("/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str) -> TaskStatus:
    """查询异步任务进度（如索引重建）。

    Args:
        task_id: 任务 ID。

    Returns:
        TaskStatus: 状态与进度。
    """
    # TODO: admin 鉴权
    # TODO: 查询任务状态存储
    raise NotImplementedError
