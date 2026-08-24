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
    graph,
    health,
    ingestion,
    metrics,
    parsing,
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
    # LangSmith 接入（单元 3.6）：env 驱动，密钥就绪后 trace 回放生效
    tracing = os.environ.get("LANGCHAIN_TRACING_V2", "false").lower() in ("1", "true")
    logger.info(
        "LangSmith tracing: %s（密钥就绪后自动生效，遗留登记见 10.x）",
        "on" if tracing else "off",
    )
    # TODO: 初始化 Neo4j 驱动、Qdrant 客户端、Redis 客户端（10.1）
    # TODO: 初始化 ES 客户端与 Postgres checkpoint 连接
    # TODO: 初始化 Embedding 服务与 LLM 注册表（fail-fast，05 §6）
    yield
    # TODO: 关闭所有数据库连接


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
        return JSONResponse(
            status_code=400,
            content={
                "code": ErrorCode.SYS_400_VALIDATION.value,
                "message": "参数校验失败",
                "detail": exc.errors(),
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
    app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(ingestion.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(parsing.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(cleaning.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(chunking.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(debug.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(communities.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(qdrant_debug.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(health.router, tags=["health"])
    app.include_router(metrics.router, tags=["metrics"])  # 单元 3.6，服务根路径

    return app


app = create_app()
