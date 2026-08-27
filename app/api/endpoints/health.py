"""
健康检查端点（02 §3.9 · 单元 10.1）。

GET /health —— 进程存活（liveness）；
GET /ready —— 七组件依赖聚合就绪（readiness）：
postgres / qdrant / neo4j / elasticsearch / redis / langgraph-server / ollama。

critical 依赖（qdrant/neo4j/elasticsearch/ollama）任一 down → 503；
Redis 与 Postgres 为 non-critical（D5/J23 降级不阻断）：down 时 /ready
仍返回 200 并携 X-Degraded（no-cache / no-persistence），由降级路径接管。
"""

# --- 标准库 ---
import asyncio
import time
from typing import Any, Awaitable, Callable

# --- 第三方库 ---
import httpx
from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

# --- 本地模块 ---
import logging

from app.api.deps import (
    get_es_client,
    get_neo4j_client,
    get_qdrant_client,
    get_redis_client,
)
from app.api.degraded import apply_degraded_header
from app.core.models import HealthComponent, HealthStatus
from app.core.config import get_settings
from app.db.es_client import ESClient
from app.db.neo4j_client import Neo4jClient
from app.db.qdrant_client import QdrantDBClient
from app.db.redis_client import RedisClient

logger = logging.getLogger(__name__)

router = APIRouter()

# critical 依赖：任一 down 则 /ready 返回 503（02 §3.9）
_CRITICAL_COMPONENTS = {"qdrant", "neo4j", "elasticsearch", "ollama"}

# 探测超时（秒，独立超时铁律 3）
_PROBE_TIMEOUT_S = 3.0


@router.get("/health", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """进程存活探针（liveness，公开）。

    Returns:
        HealthStatus: 固定 ok。
    """
    return HealthStatus(status="ok", components={})


async def _timed(check: Callable[[], Awaitable[bool]]) -> tuple[bool, int]:
    """执行探测并计时（异常视为 down）。

    Args:
        check: 异步探测函数（返回 True 表示 up）。

    Returns:
        (是否 up, 耗时毫秒)。
    """
    start = time.perf_counter()
    try:
        ok = await check()
    except Exception:  # noqa: BLE001 - 探测异常视为 down
        ok = False
    latency = int((time.perf_counter() - start) * 1000)
    return ok, latency


async def _probe_postgres() -> bool:
    """Postgres 连通探测（同步 psycopg + to_thread，兼容 Windows ProactorEventLoop）。

    psycopg 异步模式不支持 ProactorEventLoop，故用线程池执行同步连接。
    """

    def _sync_check() -> bool:
        import psycopg

        settings = get_settings()
        conn = psycopg.connect(settings.postgres_dsn, connect_timeout=int(_PROBE_TIMEOUT_S))
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        finally:
            conn.close()

    return await asyncio.to_thread(_sync_check)


async def _probe_http(url: str) -> bool:
    """HTTP GET 探测（2xx 视为 up）。

    trust_env=False：探针目标均为本机服务（ollama/langgraph-server），
    不走系统代理——否则 localhost 经代理转发会返回 502 误判 down。
    """
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S, trust_env=False) as client:
        resp = await client.get(url)
        return resp.status_code < 500


@router.get("/ready")
async def readiness_check(
    response: Response,
    neo4j: Neo4jClient = Depends(get_neo4j_client),
    qdrant: QdrantDBClient = Depends(get_qdrant_client),
    redis: RedisClient = Depends(get_redis_client),
    es: ESClient = Depends(get_es_client),
) -> Any:
    """依赖聚合就绪探针（readiness，公开）。

    Args:
        response: 响应对象（用于写 X-Degraded 头）。
        neo4j: Neo4j 客户端。
        qdrant: Qdrant 客户端。
        redis: Redis 客户端。
        es: ES 客户端。

    Returns:
        HealthStatus 聚合体；critical 任一 down 时 HTTP 503（02 §3.9）。
    """
    settings = get_settings()
    components: dict[str, HealthComponent] = {}
    degraded_reasons: list[str] = []

    probes: dict[str, Callable[[], Awaitable[bool]]] = {
        "postgres": _probe_postgres,
        "qdrant": qdrant.check_health,
        "neo4j": neo4j.check_health,
        "elasticsearch": es.check_health,
        "redis": redis.check_health,
        "langgraph-server": lambda: _probe_http(f"{settings.langgraph_server_url}/ok"),
        "ollama": lambda: _probe_http(f"{settings.ollama_base_url}/api/tags"),
    }

    # 并行探测（独立_timeout_铁律：互不阻塞）
    async def _run(name: str, probe: Callable[[], Awaitable[bool]]) -> tuple[str, bool, int]:
        ok, latency = await _timed(probe)
        return name, ok, latency

    results = await asyncio.gather(*(_run(n, p) for n, p in probes.items()))
    for name, ok, latency in results:
        if ok:
            components[name] = HealthComponent(status="up", latency_ms=latency)
        elif name in _CRITICAL_COMPONENTS:
            components[name] = HealthComponent(status="down", latency_ms=latency)
            logger.warning("健康探针 critical down: %s latency=%sms", name, latency)
        else:
            # non-critical：降级不阻断（D5/J23）
            components[name] = HealthComponent(
                status="degraded", latency_ms=latency, detail="unreachable"
            )
            if name == "redis":
                degraded_reasons.extend(["no-cache", "no-memory"])
                logger.warning("健康探针 redis degraded → X-Degraded: no-cache,no-memory（L2/工作记忆不可用，precheck 将按 miss）")
                try:
                    from app.api.metrics import record_degraded

                    record_degraded("no-cache")
                    record_degraded("no-memory")
                except Exception:
                    pass
            elif name == "postgres":
                degraded_reasons.append("no-persistence")
                logger.warning("健康探针 postgres degraded → X-Degraded: no-persistence")
                try:
                    from app.api.metrics import record_degraded

                    record_degraded("no-persistence")
                except Exception:
                    pass

    critical_down = any(
        components[c].status == "down" for c in _CRITICAL_COMPONENTS
    )
    body = HealthStatus(
        status="not_ready" if critical_down else "ready", components=components
    )

    # 响应头同步输出汇总的 X-Degraded（02 §3.9）
    apply_degraded_header(response, degraded_reasons)
    if critical_down:
        # critical 依赖 down → 503（02 §3.9），响应体仍为聚合体
        return JSONResponse(status_code=503, content=body.model_dump())
    return body
