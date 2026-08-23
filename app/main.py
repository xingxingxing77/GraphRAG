"""
FastAPI 应用入口。

创建 FastAPI 应用实例，注册路由、中间件和生命周期事件。
"""

# --- 标准库 ---
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# --- 第三方库 ---
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# --- 本地模块 ---
from app.api.endpoints import chat, health, admin
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理。

    在启动时初始化数据库连接池和 Agent 实例，
    在关闭时释放所有资源。

    Yields:
        None
    """
    # TODO: 初始化 Neo4j 驱动、Qdrant 客户端、Redis 客户端
    # TODO: 初始化 LangGraph Agent 实例
    # TODO: 初始化 Embedding 服务和 Reranker 服务
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
        description="GraphRAG 智能问答系统 API",
        lifespan=lifespan,
    )

    # 注册 CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
    app.include_router(health.router, tags=["health"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])

    return app


app = create_app()
