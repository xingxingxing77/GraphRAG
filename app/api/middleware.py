"""
中间件模块。

实现认证、限流、耗时统计中间件；限流经 RateLimiter
（Redis 固定窗口，fail-open）返回 429 + Retry-After（单元 9.2）。
"""

# --- 标准库 ---
import time

# --- 第三方库 ---
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

# --- 本地模块 ---
from app.api.rate_limit import RateLimiter

# 限流豁免路径（健康探针不受限）
_RATE_LIMIT_EXEMPT_PREFIXES = ("/health", "/ready", "/metrics")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """限流中间件（固定窗口，429 + Retry-After，单元 9.2）。

    主体解析优先级：X-API-Key → Authorization 指纹 → 客户端 IP。
    Redis 故障 fail-open（D5）；健康探针路径豁免。
    """

    def __init__(
        self,
        app: ASGIApp,
        limiter: RateLimiter | None = None,
        max_requests: int = 60,
        window_seconds: int = 60,
    ) -> None:
        """初始化限流中间件。

        Args:
            app: ASGI 应用。
            limiter: 限流器（缺省时用内存存储构建，生产注入 Redis 版）。
            max_requests: 窗口期内最大请求数。
            window_seconds: 时间窗口（秒）。
        """
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        if limiter is None:
            from app.api.rate_limit import InMemoryRateLimitStore

            limiter = RateLimiter(
                InMemoryRateLimitStore(), max_requests, window_seconds
            )
        self.limiter = limiter

    @staticmethod
    def _resolve_principal(request: Request) -> str:
        """解析限流主体（key/凭证指纹/IP）。

        Args:
            request: HTTP 请求。

        Returns:
            主体标识。
        """
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"key:{api_key[:16]}"
        auth = request.headers.get("Authorization")
        if auth:
            return f"auth:{auth[-16:]}"
        return f"ip:{request.client.host if request.client else 'unknown'}"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """处理限流逻辑（超限 429 + Retry-After）。

        Args:
            request: HTTP 请求。
            call_next: 下一个中间件/路由。

        Returns:
            HTTP 响应，超限时返回 429。
        """
        path = request.url.path
        if path.startswith(_RATE_LIMIT_EXEMPT_PREFIXES):
            return await call_next(request)

        principal = self._resolve_principal(request)
        allowed, retry_after = await self.limiter.check(principal)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "code": "AUTH_429_RATE_LIMITED",
                    "message": "请求过于频繁，请稍后重试",
                    "detail": None,
                },
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)


class TimingMiddleware(BaseHTTPMiddleware):
    """请求耗时统计中间件。

    在响应头中添加 X-Process-Time 字段。
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """统计请求处理耗时。

        Args:
            request: HTTP 请求。
            call_next: 下一个中间件/路由。

        Returns:
            带有耗时头的 HTTP 响应。
        """
        start_time = time.perf_counter()
        response = await call_next(request)
        process_time = time.perf_counter() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.4f}"
        return response
