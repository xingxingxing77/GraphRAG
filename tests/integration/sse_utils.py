"""L2 批次 SSE 联调共享工具（07 §4/§5，单元 10.4 S3）。

最小 SSE 客户端（httpx 直连 langgraph-server REST，不依赖 SDK 版本差异）：
线程创建 → runs/stream → 逐帧解析 (event, data) 序列。

服务不可达时 probe 返回 False，用例层 pytest.skip（本地单测零影响）。
"""

# --- 标准库 ---
import os
from typing import Any

# --- 第三方库 ---
import httpx

# --- 环境默认（与 .env.example / compose 对齐） ---
API_BASE = os.environ.get("L2_API_BASE", "http://localhost:8000")
AGENT_BASE = os.environ.get("L2_AGENT_BASE", "http://localhost:8001")
ASSISTANT_ID = os.environ.get("L2_ASSISTANT", "agent")
ADMIN_USERNAME = os.environ.get("L2_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("L2_ADMIN_PASSWORD", "admin-dev-password")

_PROBE_CACHE: bool | None = None


def _auth_headers(token: str) -> dict[str, str]:
    """构造 Bearer 头。

    Args:
        token: JWT。

    Returns:
        Authorization 头字典。
    """
    return {"Authorization": f"Bearer {token}"}


async def services_up() -> bool:
    """探测双服务可达性（结果缓存，进程内一次）。

    Returns:
        True = app /health 与 agent /ok 均可达。
    """
    global _PROBE_CACHE
    if _PROBE_CACHE is not None:
        return _PROBE_CACHE
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r1 = await client.get(f"{API_BASE}/health")
            r2 = await client.get(f"{AGENT_BASE}/ok")
            _PROBE_CACHE = r1.status_code == 200 and r2.status_code == 200
    except (httpx.HTTPError, OSError):
        _PROBE_CACHE = False
    return _PROBE_CACHE


async def issue_token(
    client: httpx.AsyncClient,
    *,
    grant_type: str = "password",
    username: str = ADMIN_USERNAME,
    password: str = ADMIN_PASSWORD,
    api_key: str | None = None,
    x_api_key: str | None = None,
) -> str:
    """兑换 JWT（02 §3.1）。

    Args:
        client: HTTP 客户端。
        grant_type: password | api_key。
        username: 用户名（password grant）。
        password: 密码（password grant）。
        api_key: API Key（api_key grant 请求体）。
        x_api_key: X-API-Key 头（服务兑换方式）。

    Returns:
        access_token。

    Raises:
        httpx.HTTPStatusError: 凭证错误（400/401）。
    """
    if grant_type == "api_key":
        body: dict[str, Any] = {"grant_type": "api_key", "api_key": api_key}
        headers = {"X-API-Key": x_api_key} if x_api_key else {}
    else:
        body = {"grant_type": "password", "username": username, "password": password}
        headers = {}
    r = await client.post(f"{API_BASE}/api/v1/auth/token", json=body, headers=headers)
    r.raise_for_status()
    return str(r.json()["access_token"])


async def stream_run(
    token: str,
    query: str,
    tier: str,
    *,
    session_id: str = "s_l2_smoke",
    user_id: str = "u_l2_smoke",
) -> list[tuple[str, str]]:
    """发起一次流式 run 并收集全部 (event, data) 帧（02 §4/03 §3）。

    Args:
        token: JWT。
        query: 用户查询。
        tier: latency_tier（fast/standard/deep，auto 由后端定档）。
        session_id: 会话 ID。
        user_id: 用户 ID。

    Returns:
        [(event, data_json_str), ...] 按到达顺序；HTTP 层错误抛出。
    """
    events: list[tuple[str, str]] = []
    headers = {**_auth_headers(token), "Accept": "text/event-stream"}
    async with httpx.AsyncClient(timeout=180) as client:
        r_thread = await client.post(f"{AGENT_BASE}/threads", json={}, headers=headers)
        r_thread.raise_for_status()
        tid = r_thread.json()["thread_id"]
        body = {
            "assistant_id": ASSISTANT_ID,
            "input": {
                "original_query": query,
                "session_id": session_id,
                "user_id": user_id,
            },
            "config": {"configurable": {"latency_tier": tier, "model": None}},
            "stream_mode": ["updates", "values"],
            "multitask_strategy": "interrupt",
        }
        cur_event = ""
        async with client.stream(
            "POST", f"{AGENT_BASE}/threads/{tid}/runs/stream", json=body, headers=headers
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    cur_event = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    events.append((cur_event, line[len("data:") :].strip()))
    return events
