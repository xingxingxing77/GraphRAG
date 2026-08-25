"""L2 聊天主链路自测脚本（单元 10.4，用户落地后真实测试入口）。

用途：compose 全栈起好后，一条命令跑完 07 §5 S-01~S-04 三档基准对话 +
流鉴权检查，逐项打印 PASS/FAIL 与事件时间线摘要，退出码 0=全过。

用法：
    python scripts/l2_smoke.py                        # 默认 localhost:8000/8001
    python scripts/l2_smoke.py --api http://host:8000 --agent http://host:8001

前置：
    1. docker compose up -d（五存储 + app + agent）
    2. .env 真实密钥（JWT_SECRET 双服务一致；LLM/Tavily Key 按需）
    3. curl http://localhost:8000/ready 全绿
"""

# --- 标准库 ---
import argparse
import asyncio
import json
import sys
from typing import Any

# --- 第三方库 ---
import httpx

sys.path.insert(0, ".")
from tests.integration.sse_utils import (  # noqa: E402
    AGENT_BASE,
    API_BASE,
    ASSISTANT_ID,
    issue_token,
    stream_run,
)

# 基准查询（07 §6 E-02/E-03/E-04 口径）
CASES: list[tuple[str, str, str]] = [
    ("S-02", "你好", "fast"),
    ("S-01", "清蒸鲈鱼怎么做？", "standard"),
    ("S-03", "不含海鲜的高蛋白菜有哪些？", "deep"),
]


def _values(events: list[tuple[str, str]]) -> dict[str, Any]:
    """提取 values 终态。

    Args:
        events: 帧序列。

    Returns:
        values 字典。
    """
    for event, data in events:
        if event == "values" and data:
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                return parsed
    return {}


def _nodes(events: list[tuple[str, str]]) -> list[str]:
    """提取 updates 节点序列。

    Args:
        events: 帧序列。

    Returns:
        节点名列表。
    """
    out: list[str] = []
    for event, data in events:
        if event == "updates" and data:
            parsed = json.loads(data)
            if isinstance(parsed, dict) and parsed:
                out.append(next(iter(parsed)))
    return out


def _timeline(events: list[tuple[str, str]]) -> str:
    """压缩事件时间线（每类一计数）。

    Args:
        events: 帧序列。

    Returns:
        形如 metadata×1 updates×8 values×1 end×1 的摘要。
    """
    counts: dict[str, int] = {}
    for event, _ in events:
        counts[event] = counts.get(event, 0) + 1
    return " ".join(f"{k}×{v}" for k, v in counts.items())


async def check_ready(client: httpx.AsyncClient) -> bool:
    """/ready 全绿检查。

    Args:
        client: HTTP 客户端。

    Returns:
        True = ready。
    """
    try:
        r = await client.get(f"{API_BASE}/ready")
        data = r.json()
        status = data.get("status")
        degraded = data.get("components", {})
        bad = [k for k, v in degraded.items() if isinstance(v, dict) and v.get("status") == "down"]
        print(f"[ready] status={status}" + (f" down={bad}" if bad else ""))
        return status == "ready"
    except httpx.HTTPError as exc:
        print(f"[ready] 不可达: {exc}")
        return False


async def run_case(
    client: httpx.AsyncClient, token: str, case_id: str, query: str, tier: str
) -> bool:
    """执行单条基准对话并按 07 §5 断言。

    Args:
        client: HTTP 客户端。
        token: JWT。
        case_id: 用例号。
        query: 查询。
        tier: 档位。

    Returns:
        True = PASS。
    """
    print(f"\n=== {case_id} [{tier}] {query!r} ===")
    try:
        events = await stream_run(token, query, tier)
    except httpx.HTTPStatusError as exc:
        print(f"FAIL: HTTP {exc.response.status_code}（流建立失败）")
        return False
    print(f"timeline: {_timeline(events)}  nodes={_nodes(events)}")

    values = _values(events)
    answer = values.get("answer")
    ok = bool(answer)
    detail: list[str] = []

    if case_id == "S-01":
        ok = ok and isinstance(values.get("citations"), list) and values.get("degraded") is False
        detail = ["answer 非空", "citations 列表", "degraded=False"]
    elif case_id == "S-02":
        ok = ok and "self_correction" not in _nodes(events)
        detail = ["answer 非空", "无 self_correction"]
    elif case_id == "S-03":
        score = values.get("faithfulness_score")
        ok = ok and isinstance(score, (int, float)) and 0 <= float(score) <= 1
        detail = [f"faithfulness_score={score}"]
        if ok and answer:
            detail.append(f"answer 前 60 字: {str(answer)[:60]!r}")

    print(f"checks: {', '.join(detail)}")
    print("PASS" if ok else "FAIL")
    return ok


async def main() -> int:
    """执行全部 L2 检查。

    Returns:
        0=全过，1=存在失败。
    """
    parser = argparse.ArgumentParser(description="L2 聊天主链路自测")
    parser.add_argument("--api", default=API_BASE, help="业务面基址")
    parser.add_argument("--agent", default=AGENT_BASE, help="langgraph-server 基址")
    parser.add_argument("--assistant", default=ASSISTANT_ID, help="assistant_id")
    args = parser.parse_args()

    import tests.integration.sse_utils as su

    su.API_BASE = args.api
    su.AGENT_BASE = args.agent
    su.ASSISTANT_ID = args.assistant

    results: list[tuple[str, bool]] = []
    async with httpx.AsyncClient(timeout=30) as client:
        if not await check_ready(client):
            print("\n前置未满足：/ready 未就绪。先 docker compose up -d 并核对 .env。")
            return 1
        try:
            token = await issue_token(client)
            print("[auth] password grant 兑换成功")
        except httpx.HTTPStatusError as exc:
            print(f"[auth] 兑换失败 HTTP {exc.response.status_code}（核对 admin 用户名/密码）")
            return 1

        for case_id, query, tier in CASES:
            results.append((case_id, await run_case(client, token, case_id, query, tier)))

        # S-04：坏 token 前置拒绝
        print("\n=== S-04 [fast] 坏 token ===")
        try:
            await stream_run("bad-token", "你好", "fast")
            print("FAIL: 坏 token 未被拒绝")
            results.append(("S-04", False))
        except httpx.HTTPStatusError as exc:
            ok = exc.response.status_code in (401, 403)
            print(f"HTTP {exc.response.status_code} 前置拒绝 -> {'PASS' if ok else 'FAIL'}")
            results.append(("S-04", ok))

    print("\n========== L2 汇总 ==========")
    for case_id, ok in results:
        print(f"  {case_id}: {'PASS' if ok else 'FAIL'}")
    all_ok = all(ok for _, ok in results)
    print(f"结论: {'L2 批次全部通过 ✅' if all_ok else '存在失败 ❌（按 07 §4.1 就绪矩阵处置）'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
