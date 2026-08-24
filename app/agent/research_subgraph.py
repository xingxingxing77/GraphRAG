"""
检索研究子图（B5 子图化 · E2 HITL 预留 · 单元 5.7）。

将「检索 → 融合」封装为 ToolRouter 可调用的独立单元：
- 六路并行（asyncio.gather, return_exceptions=True，单路失败不阻塞）；
- 整轮调用结果经 run 内缓存复用（B5），避免重复检索；
- LangSmith 中子图 span 天然分层（05 §7）；
- interrupt() HITL 挂点预留（E2，开关 agent.hitl.enabled 默认 false）。
"""

# --- 标准库 ---
import asyncio
import logging
from pathlib import Path
from typing import Any

# --- 本地模块 ---
from app.agent.nodes.tool_router import _get_retriever_hub, dedupe_by_result_id
from app.agent.state import AgentState
from app.core.models import RetrievalResult
from app.retrieval.fusion import FusionEngine

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "pipeline_config.yaml"

# 整轮研究缓存（B5：整轮结果可复用；生命周期 run 内，clear_round_cache 清理）
_ROUND_CACHE: dict[str, list[RetrievalResult]] = {}

# 单轮融合输出上限（粗排 Top-20）
_RESEARCH_TOP_N = 20


def _hitl_enabled() -> bool:
    """读取 E2 HITL 开关（agent.hitl.enabled，默认 false）。

    Returns:
        True 表示启用 interrupt 挂点。
    """
    try:
        import yaml

        with open(_CONFIG_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return bool(((cfg.get("agent") or {}).get("hitl") or {}).get("enabled", False))
    except Exception:  # noqa: BLE001 - 配置缺失默认关闭
        return False


def clear_round_cache() -> None:
    """清空整轮研究缓存（新 run 开始时调用）。"""
    _ROUND_CACHE.clear()


async def research_subgraph(state: AgentState) -> dict[str, Any]:
    """执行一轮完整研究：六路并行检索 → 融合。

    Args:
        state: 当前 Agent 状态（读取 query/retrieved_evidence）。

    Returns:
        状态增量更新：retrieved_evidence 合并去重、retrieval_rounds +1。

    Raises:
        GraphInterrupt: hitl 启用时的 interrupt 挂点（E2，待人工确认）。
    """
    query = state.get("query") or state.get("original_query", "")

    # E2 HITL 挂点（默认关闭；开启后高成本检索前暂停等待确认）
    if _hitl_enabled():
        from langgraph.types import interrupt

        interrupt({"type": "research_confirm", "query": query})

    # B5 整轮缓存复用：同查询不重复检索
    if query in _ROUND_CACHE:
        fused = _ROUND_CACHE[query]
    else:
        fused = await _run_research(query)
        _ROUND_CACHE[query] = fused

    # fan-in 合并去重 + 轮次计数
    existing = list(state.get("retrieved_evidence") or [])
    merged = dedupe_by_result_id(existing + fused)
    return {
        "retrieved_evidence": merged,
        "retrieval_rounds": int(state.get("retrieval_rounds", 0)) + 1,
    }


async def _run_research(query: str) -> list[RetrievalResult]:
    """六路并行检索 + 融合（单路失败降级空列表）。

    Args:
        query: 研究查询。

    Returns:
        融合后 Top-N 证据列表。
    """
    try:
        hub = await _get_retriever_hub()
    except Exception as exc:  # noqa: BLE001 - 依赖不可用返回空
        logger.warning("research_subgraph 检索器不可用: %s", exc)
        return []

    names = list(hub.keys())
    gathered = await asyncio.gather(
        *(hub[name].retrieve(query, _RESEARCH_TOP_N) for name in names),
        return_exceptions=True,
    )
    grouped: dict[str, list[RetrievalResult]] = {}
    for name, result in zip(names, gathered):
        if isinstance(result, BaseException):
            logger.warning("research 路 %s 失败（降级空列表）: %s", name, result)
            grouped[name] = []
        else:
            hit_list: list[RetrievalResult] = list(result)
            grouped[name] = hit_list
    return FusionEngine().fuse(grouped, top_n=_RESEARCH_TOP_N)
