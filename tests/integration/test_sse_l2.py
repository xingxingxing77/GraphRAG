"""L2 聊天主链路联调用例（07 §5 S-01~S-04，单元 10.4 S3）。

前置（用户落地后自测）：
    1. docker compose up -d          # 五存储 + app:8000 + agent:8001
    2. .env 填真实密钥（JWT_SECRET 双服务一致）
    3. pytest tests/integration -v   # 服务不可达自动 skip

断言口径（07 §5）：
    S-01 standard 全链：metadata → updates≥1 → values → end；values 含
        answer(非空)/citations/degraded=false
    S-02 chitchat fast：无 self_correction updates；values 存在
    S-03 deep 多跳：values.faithfulness_score 存在且 [0,1]；设
        L2_FAITH_MIN 环境变量时追加 ≥ 阈值断言（默认不设，避免弱模型误报）
    S-04 流鉴权失效：坏 token → HTTP 4xx 前置拒绝
"""

# --- 标准库 ---
import json
import os

# --- 第三方库 ---
import httpx
import pytest

# --- 本地模块 ---
from tests.integration.sse_utils import (
    AGENT_BASE,
    issue_token,
    services_up,
    stream_run,
)

pytestmark = pytest.mark.asyncio


async def _skip_if_down() -> None:
    """服务不可达时跳过（07 §4 L2 批次前置未满足）。"""
    if not await services_up():
        pytest.skip("L2 前置未满足：app:8000 / agent:8001 不可达（compose up 后重跑）")


async def _token(client: httpx.AsyncClient) -> str:
    """兑换有效 JWT。"""
    return await issue_token(client)


def _values_payload(events: list[tuple[str, str]]) -> dict[str, object]:
    """提取 values 终态载荷。

    Args:
        events: (event, data) 帧序列。

    Returns:
        values 的 JSON 字典（缺失时空字典）。
    """
    for event, data in events:
        if event == "values" and data:
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                return parsed
    return {}


def _update_nodes(events: list[tuple[str, str]]) -> list[str]:
    """提取 updates 帧的节点名序列。

    Args:
        events: (event, data) 帧序列。

    Returns:
        节点名列表（保持到达顺序）。
    """
    nodes: list[str] = []
    for event, data in events:
        if event != "updates" or not data:
            continue
        parsed = json.loads(data)
        if isinstance(parsed, dict) and parsed:
            nodes.append(next(iter(parsed)))
    return nodes


class TestL2SseBatch:
    """L2 批次：三档基准对话 + 流鉴权（07 §4.1 L2 就绪标准）。"""

    async def test_s01_standard_full_chain(self, client: httpx.AsyncClient) -> None:
        """S-01：standard 全链事件序列与 values 终态字段齐全。"""
        await _skip_if_down()
        token = await _token(client)
        events = await stream_run(token, "清蒸鲈鱼怎么做？", "standard")

        kinds = [e for e, _ in events]
        assert "metadata" in kinds, f"缺 metadata 帧: {kinds}"
        assert "values" in kinds, f"缺 values 终态帧: {kinds}"
        assert len(_update_nodes(events)) >= 1, "updates 帧为空（thought 无来源）"

        values = _values_payload(events)
        assert isinstance(values.get("answer"), str) and values["answer"], "answer 缺失或为空"
        assert isinstance(values.get("citations"), list), "citations 缺失或非列表"
        assert values.get("degraded") is False, "standard 档不应降级"

    async def test_s02_chitchat_fast(self, client: httpx.AsyncClient) -> None:
        """S-02：chitchat fast 无 self_correction（E-02 口径）。"""
        await _skip_if_down()
        token = await _token(client)
        events = await stream_run(token, "你好", "fast")

        nodes = _update_nodes(events)
        assert "self_correction" not in nodes, f"fast 档不应有忠实度校验: {nodes}"
        assert _values_payload(events).get("answer"), "fast 档 values 缺 answer"

    async def test_s03_deep_multihop(self, client: httpx.AsyncClient) -> None:
        """S-03：deep 多跳，终态忠实度分数字段齐全（阈值可经 L2_FAITH_MIN 收紧）。"""
        await _skip_if_down()
        token = await _token(client)
        events = await stream_run(token, "不含海鲜的高蛋白菜有哪些？", "deep")

        values = _values_payload(events)
        score = values.get("faithfulness_score")
        assert isinstance(score, (int, float)), f"values 缺 faithfulness_score: {sorted(values)}"
        assert 0 <= float(score) <= 1, f"忠实度分数越界: {score}"
        faith_min = os.environ.get("L2_FAITH_MIN")
        if faith_min:
            assert float(score) >= float(faith_min), f"忠实度 {score} < 阈值 {faith_min}"

    async def test_s04_stream_auth_invalid(self, client: httpx.AsyncClient) -> None:
        """S-04：坏 token 流建立前被拒（HTTP 4xx 前置拒绝，03 §6）。"""
        await _skip_if_down()
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await stream_run("bad-token", "你好", "fast")
        assert exc_info.value.response.status_code in (401, 403), (
            f"坏 token 应 401/403 前置拒绝: {exc_info.value.response.status_code}"
        )


async def test_agent_auth_shared_secret(client: httpx.AsyncClient) -> None:
    """补充：业务面签发的 JWT 可通过 agent custom auth（J19 同源密钥）。"""
    await _skip_if_down()
    token = await _token(client)
    async with httpx.AsyncClient(timeout=10) as raw:
        r = await raw.get(f"{AGENT_BASE}/helpers/threads", headers={"Authorization": f"Bearer {token}"})
    # /helpers/threads 为 server 内建 UI 辅助端点；可达且非 401 即证明同源密钥生效
    assert r.status_code != 401, "agent custom auth 未接受业务面 JWT（JWT_SECRET 不一致？）"
