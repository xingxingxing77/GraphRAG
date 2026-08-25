"""L2 联调批次 fixtures（httpx 异步客户端）。"""

# --- 第三方库 ---
import httpx
import pytest


@pytest.fixture
async def client():
    """提供异步 HTTP 客户端（用例级生命周期）。

    Yields:
        httpx.AsyncClient。
    """
    async with httpx.AsyncClient(timeout=30) as c:
        yield c
