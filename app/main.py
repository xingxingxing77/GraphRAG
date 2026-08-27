"""
FastAPI 应用入口（业务面 :8000，J19）。

创建 FastAPI 应用实例，注册路由、中间件和生命周期事件。
聊天主链路在 langgraph-server :8001（前端 SDK 直连），
本服务仅承载业务面端点（架构 §3.6 全集）。
"""

# --- 标准库 ---
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# --- 第三方库 ---
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# --- 本地模块 ---
from app.api.endpoints import (
    admin,
    auth,
    chat,
    chunking,
    cleaning,
    communities,
    config,
    debug,
    feedback,
    golden,
    graph,
    health,
    ingestion,
    metrics,
    parsing,
    prompt_bar,
    qdrant_debug,
    sessions,
)
from app.api.errors import ApiError, ErrorCode
from app.core.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理。

    在启动时初始化数据库连接池和 Agent 实例，
    在关闭时释放所有资源。

    Yields:
        None
    """
    # 生产密钥强校验（fail-fast，P0-01）
    try:
        get_settings().validate_prod_secrets()
    except SystemExit as exc:
        logger.critical("配置校验失败拒绝启动: %s", exc)
        raise

    # LangSmith 接入（单元 3.6）：env 驱动，密钥就绪后 trace 回放生效
    tracing = os.environ.get("LANGCHAIN_TRACING_V2", "false").lower() in ("1", "true")
    logger.info(
        "LangSmith tracing: %s（密钥就绪后自动生效，遗留登记见 10.x）",
        "on" if tracing else "off",
    )
    # 预热核心依赖（P0-02/P0-03：避免首请求冷启动竞态与连接泄漏）
    try:
        from app.api.deps import get_qdrant_client, get_redis_client

        # 仅预热轻量客户端；Embedding/LLM 仍惰性加载（模型体积大）
        async for _ in get_qdrant_client():
            pass
        async for _ in get_redis_client():
            pass
        logger.info("核心存储客户端预热完成（Qdrant/Redis）")
    except Exception as exc:  # noqa: BLE001 - 预热失败不阻塞启动，首请求降级
        logger.warning("存储客户端预热失败（首请求惰性重试）: %s", exc)
    yield
    # 优雅关闭（P0-02）
    try:
        from app.api.deps import close_all_clients

        await close_all_clients()
        logger.info("全部客户端连接已关闭")
    except Exception as exc:  # noqa: BLE001
        logger.warning("关闭客户端时异常: %s", exc)


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。

    Returns:
        FastAPI: 配置完成的应用实例。
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="GraphRAG 智能问答系统 · 业务面 API（J19）",
        lifespan=lifespan,
    )

    # CORS：显式 origin 白名单（架构第 1 层注——allow_origins=["*"] 与
    # allow_credentials=True 组合被浏览器规范禁止；开发期含 Vite dev 源）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Degraded"],
    )

    # 全局限流（单元 9.2，D6）：默认关闭，生产经 RATE_LIMIT_ENABLED 开启
    if settings.rate_limit_enabled:
        from app.api.middleware import RateLimitMiddleware

        app.add_middleware(
            RateLimitMiddleware,
            max_requests=settings.rate_limit_max_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )

    # --- 统一错误体（02 §2.3 {code, message, detail}） ---
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        """将 ApiError 转为统一错误体 JSON 响应。"""
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code.value, "message": exc.message, "detail": exc.detail},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Pydantic 校验失败 → 400 SYS_400_VALIDATION（02 §2.3/§6，v1.1 补登）。"""
        # exc.errors() 的 ctx 可能含 ValueError 等不可 JSON 序列化对象，需经 jsonable_encoder
        from fastapi.encoders import jsonable_encoder

        return JSONResponse(
            status_code=400,
            content={
                "code": ErrorCode.SYS_400_VALIDATION.value,
                "message": "参数校验失败",
                "detail": jsonable_encoder(exc.errors()),
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """框架层 HTTP 异常 → 统一错误体（404 归 SYS_404_NOT_FOUND）。"""
        code = (
            ErrorCode.SYS_404_NOT_FOUND.value
            if exc.status_code == 404
            else ErrorCode.SYS_500_INTERNAL.value
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": code,
                "message": str(exc.detail),
                "detail": None,
            },
        )

    # --- 路由注册（端点全集见架构 §3.6 / 02 §3） ---
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["sessions"])
    app.include_router(feedback.router, prefix="/api/v1/feedback", tags=["feedback"])
    app.include_router(graph.router, prefix="/api/v1/graph", tags=["graph"])
    app.include_router(config.router, prefix="/api/v1/config", tags=["config"])
    app.include_router(prompt_bar.router, prefix="/api/v1/prompt-bar", tags=["prompt-bar"])
    app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(ingestion.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(parsing.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(cleaning.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(chunking.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(debug.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(communities.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(qdrant_debug.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(golden.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(health.router, tags=["health"])
    app.include_router(metrics.router, tags=["metrics"])  # 单元 3.6，服务根路径

    return app


app = create_app()
