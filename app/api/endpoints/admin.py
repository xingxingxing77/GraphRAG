"""管理接口端点组（02 §3.10 · 单元 10.6 收口）。

统一约定：鉴权 JWT 且 role=admin（security.require_admin），否则
AUTH_403_FORBIDDEN；全部写审计日志（rag.audit logger，经 security.MaskingFilter
脱敏后落结构化日志）。

异步任务：索引重建经 asyncio.create_task + 进程内注册表真异步执行
（02 §3.10 tasks 进度轮询契约）；重建语义 = 校验与修复（约束确保/
索引确保/死信重放），全量重嵌入属 J18 禁热更路径、须管道重跑。
"""

# --- 标准库 ---
import asyncio
import logging
import uuid
from typing import Literal
from datetime import UTC, datetime

# --- 第三方库 ---
import yaml
from fastapi import APIRouter, Body, Depends
from pydantic import ValidationError

# --- 本地模块 ---
from app.api.deps import get_neo4j_client, get_semantic_cache
from app.api.errors import ApiError, ErrorCode
from app.api.security import require_admin
from app.core.config import get_settings
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
from app.db.es_client import ESClient
from app.db.neo4j_client import Neo4jClient
from app.db.redis_client import RedisClient
from app.memory.semantic_cache import SemanticCache
from app.pipeline.config import load_pipeline_config

router = APIRouter()

# 审计日志（操作人/时间/动作/明细；脱敏由 security.MaskingFilter 链路负责）
audit_log = logging.getLogger("rag.audit")

# ── 异步任务注册表（进程内；02 §3.10 GET /admin/tasks/{id} 数据源） ──


class _TaskRecord:
    """异步任务记录（重建任务生命周期：running → done/failed）。

    Attributes:
        task_id: 任务 ID（t_<uuid>）。
        scope: 重建范围（vector/graph/fulltext/all）。
        state: running | done | failed。
        progress: 进度 [0,1]。
        error: 失败原因（state=failed 时）。
    """

    def __init__(self, task_id: str, scope: str) -> None:
        self.task_id = task_id
        self.scope = scope
        self.state: Literal["running", "done", "failed"] = "running"
        self.progress = 0.0
        self.error: str | None = None


_tasks: dict[str, _TaskRecord] = {}
_rebuild_lock = asyncio.Lock()


def _audit(user: dict[str, object], action: str, detail: str) -> None:
    """写审计日志（操作人/时间/动作/明细）。

    Args:
        user: require_admin 产出的 JWT payload。
        action: 动作名（如 cache.clear）。
        detail: 明细摘要。
    """
    audit_log.info(
        "admin action=%s user=%s at=%s detail=%s",
        action,
        user.get("sub", "?"),
        datetime.now(UTC).isoformat(),
        detail,
    )


async def _run_rebuild(task_id: str, scope: str, full: bool) -> None:
    """执行重建任务（后台协程）：校验与修复语义。

    步骤（按 scope 展开，进度逐段推进）：
      vector   → Qdrant check_health（集合连通性）
      graph    → Neo4j ensure_constraints（唯一约束/索引确保）+ 实体计数
      fulltext → ES ensure_indices + 死信队列重放（ESSyncer）+ 计数

    Args:
        task_id: 注册表任务 ID。
        scope: vector | graph | fulltext | all。
        full: 全量标记（当前语义下约束/索引确保与增量一致；全量重嵌入
            属 J18 禁热更路径，须管道重跑，见 docstring 顶部说明）。
    """
    rec = _tasks[task_id]
    settings = get_settings()
    es: ESClient | None = None
    neo: Neo4jClient | None = None
    try:
        scopes = ["vector", "graph", "fulltext"] if scope == "all" else [scope]
        for i, sc in enumerate(scopes):
            if sc == "vector":
                from app.db.qdrant_client import QdrantDBClient

                qd = QdrantDBClient(settings.qdrant_host, settings.qdrant_port)
                if not await qd.check_health():
                    raise RuntimeError("Qdrant check_health 失败")
            elif sc == "graph":
                neo = Neo4jClient(
                    settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password
                )
                await neo.connect()
                await neo.ensure_constraints()
                rows = await neo.execute_cypher(
                    "MATCH (e:Entity) RETURN count(e) AS n"
                )
                audit_log.info("rebuild graph entities=%s", rows[0]["n"] if rows else 0)
            else:  # fulltext
                es = ESClient(settings.elasticsearch_host)
                await es.connect()
                await es.ensure_indices()
                from app.db.redis_client import RedisClient
                from app.pipeline.indexing.fulltext_indexer import ESSyncer

                redis = RedisClient(settings.redis_host, settings.redis_port)
                await redis.connect()
                syncer = ESSyncer(es, redis)
                replayed = await syncer.replay_dead_letter(max_items=500)
                chunks = await es.count("rag_chunks")
                audit_log.info(
                    "rebuild fulltext replayed=%s chunks=%s", replayed, chunks
                )
                await redis.close()
            rec.progress = (i + 1) / len(scopes)
        rec.state = "done"
        rec.progress = 1.0
    except Exception as exc:  # noqa: BLE001 - 后台任务兜底，状态落注册表
        rec.state = "failed"
        rec.error = str(exc)
        audit_log.error("rebuild failed task=%s err=%s", task_id, exc)
    finally:
        if es is not None:
            await es.close()
        if neo is not None:
            await neo.close()


# ── 端点 ──────────────────────────────────────────────


@router.post("/cache/clear", response_model=CacheClearResponse)
async def clear_cache(
    request: CacheClearRequest = Body(...),
    user: dict[str, object] = Depends(require_admin),
    cache: SemanticCache = Depends(get_semantic_cache),
) -> CacheClearResponse:
    """按 scope/doc_id 清除缓存（失效联动）。

    Args:
        request: 清理范围与可选 doc_id。
        user: admin payload。
        cache: 语义缓存（依赖注入）。

    Returns:
        CacheClearResponse: 清除条目数。
    """
    purged = 0
    if request.doc_id:
        purged = await cache.invalidate_doc(request.doc_id)
    else:
        settings = get_settings()
        if request.scope in ("l1", "all"):
            # L1 无原生 TTL：以远期 now 触发全量过期清理（04 §7.1）
            purged += await cache.purge_expired(now=2**31)
        if request.scope in ("l2", "all"):
            redis = RedisClient(settings.redis_host, settings.redis_port)
            await redis.connect()
            try:
                purged += await redis.scan_and_delete("l2:ret:*")
            finally:
                await redis.close()
    _audit(user, "cache.clear", f"scope={request.scope} doc_id={request.doc_id} purged={purged}")
    return CacheClearResponse(purged=purged)


@router.post("/index/rebuild", status_code=202, response_model=TaskAccepted)
async def rebuild_index(
    request: IndexRebuildRequest = Body(...),
    user: dict[str, object] = Depends(require_admin),
) -> TaskAccepted:
    """触发索引异步重建（vector/graph/fulltext/all）。

    Args:
        request: 重建范围与是否全量。
        user: admin payload。

    Returns:
        TaskAccepted: 任务 ID（进度查 GET /admin/tasks/{task_id}）。

    Raises:
        ApiError: ADMIN_409_TASK_RUNNING（已有重建任务执行中）。
    """
    async with _rebuild_lock:
        running = [t for t in _tasks.values() if t.state == "running"]
        if running:
            raise ApiError(
                ErrorCode.ADMIN_409_TASK_RUNNING,
                f"已有重建任务执行中: {running[0].task_id}",
            )
        task_id = f"t_{uuid.uuid4().hex[:12]}"
        _tasks[task_id] = _TaskRecord(task_id, request.scope)
        asyncio.create_task(_run_rebuild(task_id, request.scope, request.full))
    _audit(user, "index.rebuild", f"scope={request.scope} full={request.full} task={task_id}")
    return TaskAccepted(task_id=task_id)


@router.put("/config/hot-reload", response_model=HotReloadResponse)
async def hot_reload_config(
    user: dict[str, object] = Depends(require_admin),
) -> HotReloadResponse:
    """J18 受限热更：清洗规则/检索权重/降级参数/agent.* 效率参数。

    重读可热更 YAML 并 pydantic 重校验（D7 fail-fast 语义：错误进
    errors 列表而非中断）；分块参数与 embedding 模型禁止热更（01 §7）。

    Args:
        user: admin payload。

    Returns:
        HotReloadResponse: 重载成功的配置名与错误列表。
    """
    reloaded: list[str] = []
    errors: list[str] = []

    # pipeline_config：pydantic 全量重校验（检索权重/降级参数所在）
    try:
        load_pipeline_config()
        reloaded.append("pipeline_config")
    except (ValidationError, OSError, yaml.YAMLError) as exc:
        errors.append(f"pipeline_config: {exc}")

    # cleaning_rules / reliability：结构级重校验（可热更组，J18）
    for name, path in (
        ("cleaning_rules", "config/cleaning_rules.yaml"),
        ("reliability", "config/reliability.yaml"),
    ):
        try:
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not isinstance(data, dict) or not data:
                raise ValueError("空配置或结构非法")
            reloaded.append(name)
        except (OSError, yaml.YAMLError, ValueError) as exc:
            errors.append(f"{name}: {exc}")

    _audit(user, "config.hot_reload", f"reloaded={reloaded} errors={len(errors)}")
    return HotReloadResponse(reloaded=reloaded, errors=errors)


@router.get("/review-queue", response_model=Paged[ReviewQueueItem])
async def list_review_queue(
    user: dict[str, object] = Depends(require_admin),
    neo: Neo4jClient = Depends(get_neo4j_client),
    cursor: str | None = None,
    limit: int = 20,
) -> Paged[ReviewQueueItem]:
    """开放区实体人工审核队列（J12，按出现频次排序）。

    Args:
        user: admin payload。
        neo: Neo4j 客户端。
        cursor: 分页游标（上一页末尾的 skip 值）。
        limit: 每页数量（≤100）。

    Returns:
        Paged[ReviewQueueItem]: 待审核实体列表。

    Raises:
        ApiError: GRAPH_503_STORE_UNAVAILABLE（Neo4j 不可用）。
    """
    skip = int(cursor) if cursor and cursor.isdigit() else 0
    limit = min(max(limit, 1), 100)
    try:
        rows = await neo.execute_cypher(
            "MATCH (e:Entity {zone: 'open', status: 'pending'}) "
            "RETURN e.canonical_name AS entity_id, coalesce(e.name, e.canonical_name) AS name, "
            "coalesce(e.freq, 0) AS freq, e.first_seen AS first_seen "
            "ORDER BY coalesce(e.freq, 0) DESC SKIP $skip LIMIT $limit",
            {"skip": skip, "limit": limit + 1},
        )
    except Exception as exc:  # noqa: BLE001 - 存储不可达走 503 降级语义
        raise ApiError(
            ErrorCode.GRAPH_503_STORE_UNAVAILABLE, "Neo4j 不可用"
        ) from exc
    has_more = len(rows) > limit
    items = [
        ReviewQueueItem(
            entity_id=str(r["entity_id"]),
            name=str(r["name"]),
            freq=int(r.get("freq") or 0),
            first_seen=r.get("first_seen"),
        )
        for r in rows[:limit]
    ]
    return Paged(
        items=items,
        next_cursor=str(skip + limit) if has_more else None,
    )


@router.post("/review/decision", response_model=FeedbackResponse)
async def review_decision(
    request: ReviewDecisionRequest,
    user: dict[str, object] = Depends(require_admin),
    neo: Neo4jClient = Depends(get_neo4j_client),
) -> FeedbackResponse:
    """审核决定：approve 升级白名单（zone/status）并按 graph_schema
    重放可判定的关联三元组；reject 标记拒绝。

    Args:
        request: 实体 ID + 决定。
        user: admin payload。
        neo: Neo4j 客户端。

    Returns:
        FeedbackResponse: {ok: true}。

    Raises:
        ApiError: GRAPH_404_ENTITY_NOT_FOUND（实体不存在）。
    """
    from app.pipeline.graph_construction.schema import load_graph_schema

    schema = load_graph_schema()
    if request.action == "approve":
        rows = await neo.execute_cypher(
            "MATCH (e:Entity {canonical_name: $name}) "
            "SET e.zone='core', e.status='approved' "
            "RETURN e.type AS type LIMIT 1",
            {"name": request.entity_id},
        )
        if not rows:
            raise ApiError(
                ErrorCode.GRAPH_404_ENTITY_NOT_FOUND,
                f"实体不存在: {request.entity_id}",
            )
        from_type = str(rows[0].get("type") or "Other")
        # G4 三元组重放（可判定子集）：泛化 :REL 边若与白名单唯一匹配，
        # 则补写同义白名单关系（04 §5.4 升级机制）
        rels = await neo.execute_cypher(
            "MATCH (e:Entity {canonical_name: $name})-[r:REL]-(n:Entity) "
            "RETURN type(r) AS rt, n.type AS nt, "
            "CASE WHEN startNode(r) = e THEN 1 ELSE 0 END AS outgoing",
            {"name": request.entity_id},
        )
        for rel in rels:
            to_type = str(rel.get("nt") or "Other")
            outgoing = bool(rel.get("outgoing"))
            allowed = [
                spec.rel_type
                for spec in getattr(schema, "edge_types", [])
                if schema.is_allowed_edge(from_type, spec.rel_type, to_type)
                and spec.rel_type not in ("REL", "MENTIONS")
            ]
            if len(allowed) != 1:
                continue
            if outgoing:
                await neo.execute_cypher(
                    "MATCH (a:Entity {canonical_name: $a})-[r:REL]->(b:Entity {canonical_name: $b}) "
                    f"MERGE (a)-[:{allowed[0]}]->(b)",
                    {"a": request.entity_id, "b": str(rel.get("nt"))},
                )
            else:
                await neo.execute_cypher(
                    "MATCH (a:Entity {canonical_name: $a})<-[r:REL]-(b:Entity {canonical_name: $b}) "
                    f"MERGE (a)<-[:{allowed[0]}]-(b)",
                    {"a": request.entity_id, "b": str(rel.get("nt"))},
                )
    else:
        rows = await neo.execute_cypher(
            "MATCH (e:Entity {canonical_name: $name}) "
            "SET e.status='rejected' RETURN e.canonical_name LIMIT 1",
            {"name": request.entity_id},
        )
        if not rows:
            raise ApiError(
                ErrorCode.GRAPH_404_ENTITY_NOT_FOUND,
                f"实体不存在: {request.entity_id}",
            )
    _audit(user, "review.decision", f"entity={request.entity_id} action={request.action}")
    return FeedbackResponse(ok=True)


@router.get("/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(
    task_id: str,
    user: dict[str, object] = Depends(require_admin),
) -> TaskStatus:
    """查询异步任务进度（如索引重建）。

    Args:
        task_id: 任务 ID。
        user: admin payload。

    Returns:
        TaskStatus: 状态与进度。

    Raises:
        ApiError: SYS_404_NOT_FOUND（任务不存在）。
    """
    rec = _tasks.get(task_id)
    if rec is None:
        raise ApiError(ErrorCode.SYS_404_NOT_FOUND, f"任务不存在: {task_id}")
    return TaskStatus(state=rec.state, progress=rec.progress)

