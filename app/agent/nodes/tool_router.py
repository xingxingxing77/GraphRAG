"""
工具路由节点（架构 L6 · A1/E3/B3 · 单元 5.3）。

职责：
- 执行 plan 中待处理的检索步骤（direct_answer 零执行，J9）；
- A1：deep 档无依赖步骤 asyncio.gather 并行扇出（standard/fast 串行；
  完整 LangGraph Send map-reduce 化随 5.7 检索子图化落地）；
- E3：run 内 (tool, query) 规范 hash 记忆化，命中不二次调用；
- fan-in：按 result_id 合并去重 + retrieval_rounds 统一 +1；
- B3：轮间修剪（keep_score 保留线 + content 截长），在写入
  checkpoint 之前执行，防 Postgres payload 膨胀。
"""

# --- 标准库 ---
import asyncio
import hashlib
import logging
import os
from typing import Any

import yaml

# --- 本地模块 ---
from app.agent.state import AgentState
from app.core.models import PlanStep, RetrievalResult, SourceKind
from app.db.collections import is_business_collection
from app.retrieval.base import BaseRetriever
from app.retrieval.dense_retriever import DenseRetriever
from app.retrieval.fulltext_retriever import FullTextRetriever
from app.retrieval.global_retriever import GlobalRetriever
from app.retrieval.graph_retriever import GraphRetriever
from app.retrieval.sparse_retriever import SparseRetriever
from app.retrieval.web_retriever import WebRetriever

logger = logging.getLogger(__name__)

# 六路检索源白名单（与 SourceKind 对齐）
_ALLOWED_TOOLS = {s.value for s in SourceKind}

# 每步召回数（粗排口径）
_STEP_TOP_K = 10

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
    "pipeline_config.yaml",
)
# 启动期缓存 agent 配置，避免首个 async 节点内读盘触发 Blocking
_AGENT_CFG_CACHE: dict[str, Any] | None = None
try:
    with open(_CONFIG_PATH, encoding="utf-8") as _f:
        _raw_cfg = yaml.safe_load(_f) or {}
        _AGENT_CFG_CACHE = _raw_cfg.get("agent") or None
except Exception:
    _AGENT_CFG_CACHE = None


def _load_agent_config() -> dict[str, Any]:
    """读取 pipeline_config.yaml agent 段（启动期已缓存，async 内零 I/O）。

    Returns:
        agent 配置字典（含 parallel_fanout/tool_memo/evidence_prune）。
    """
    defaults: dict[str, Any] = {
        "parallel_fanout": "deep_only",
        "tool_memo": {"enabled": True},
        "evidence_prune": {"keep_score": 0.25, "max_content_chars": 600},
    }
    if _AGENT_CFG_CACHE is not None:
        return {**defaults, **_AGENT_CFG_CACHE}
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        agent_cfg = cfg.get("agent") or {}
        return {**defaults, **agent_cfg}
    except Exception:  # noqa: BLE001 - 配置缺失用默认
        return defaults


def memo_key(tool: str, query: str) -> str:
    """计算 E3 记忆化键：(tool, query) 规范 hash。

    Args:
        tool: 工具名。
        query: 检索查询（小写去空白归一）。

    Returns:
        sha256 前 24 位十六进制。
    """
    normalized = f"{tool}|{query.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def prune_evidence(
    evidence: list[RetrievalResult],
    keep_score: float = 0.25,
    max_content_chars: int = 600,
) -> list[RetrievalResult]:
    """B3 轮间修剪：result_id 去重 + 低分剔除 + content 截长。

    Args:
        evidence: 累积证据列表。
        keep_score: 保留分线（低于该分剔除；粗排融合分口径）。
        max_content_chars: content 截长上限（保留引用定位所需最小字段）。

    Returns:
        修剪后的证据列表（原序保持）。
    """
    seen: set[str] = set()
    pruned: list[RetrievalResult] = []
    for r in evidence:
        if r.result_id in seen:
            continue
        seen.add(r.result_id)
        if r.score < keep_score:
            continue
        content = r.content
        if len(content) > max_content_chars:
            content = content[:max_content_chars]
            pruned.append(r.model_copy(update={"content": content}))
        else:
            pruned.append(r)
    return pruned


def dedupe_by_result_id(
    evidence: list[RetrievalResult],
) -> list[RetrievalResult]:
    """fan-in 合并去重（按 result_id，保留首次出现）。

    Args:
        evidence: 合并后的证据列表。

    Returns:
        去重后的列表（原序保持）。
    """
    seen: set[str] = set()
    merged: list[RetrievalResult] = []
    for r in evidence:
        if r.result_id in seen:
            continue
        seen.add(r.result_id)
        merged.append(r)
    return merged


async def _execute_tool(tool: str, query: str, top_k: int) -> list[RetrievalResult]:
    """执行单路检索（测试可替换；实际分发至六路检索器）。

    Args:
        tool: 检索源名（六路枚举值）。
        query: 检索查询。
        top_k: 召回数。

    Returns:
        检索结果列表；失败/未接入返回空列表（D5）。
    """
    try:
        hub = await _get_retriever_hub()
    except Exception as exc:  # noqa: BLE001 - 依赖不可用降级空列表
        logger.warning("检索器初始化失败（%s 路降级）: %s", tool, exc)
        return []
    retriever = hub.get(tool)
    if retriever is None:
        return []
    return await retriever.retrieve(query, top_k)


async def tool_router_node(state: AgentState) -> dict[str, Any]:
    """工具路由节点：执行计划步骤并 fan-in 合并。

    Args:
        state: 当前 Agent 状态。

    Returns:
        状态增量：retrieved_evidence（修剪后全量）/ tool_call_cache /
        plan（步骤置 done）/ current_step / retrieval_rounds（+1）。
    """
    plan = list(state.get("plan") or [])
    # direct_answer 零执行（J9）：不产生证据、不计轮次
    if len(plan) == 1 and plan[0].tool == "direct_answer":
        return {}

    agent_cfg = _load_agent_config()
    memo_enabled = bool((agent_cfg.get("tool_memo") or {}).get("enabled", True))
    parallel_fanout = str(agent_cfg.get("parallel_fanout", "deep_only"))

    # E-07：图谱系检索器（graph/global/fulltext）故障 → no-graph 降级原因（9.1）
    degraded_reasons: list[str] = []
    try:
        hub_snapshot = await _get_retriever_hub()
        graph_family_errors_before = sum(
            getattr(hub_snapshot.get(name), "error_count", 0)
            for name in ("graph", "global", "fulltext")
        )
    except Exception:  # noqa: BLE001 - hub 不可用时无法快照
        graph_family_errors_before = 0

    pending = [s for s in plan if s.status != "done"]
    cache: dict[str, RetrievalResult] = dict(state.get("tool_call_cache") or {})
    cache_updates: dict[str, RetrievalResult] = {}

    async def run_step(step: PlanStep) -> list[RetrievalResult]:
        """执行单步（E3 记忆化命中直接返回，不二次调用）。

        记忆化按架构 §3.4 类型 dict[str, RetrievalResult] 缓存首位结果
        （结果已按分降序，首位为最高置信条目）。
        """
        if step.tool not in _ALLOWED_TOOLS:
            return []
        key = memo_key(step.tool, step.query)
        if memo_enabled and key in cache:
            return [cache[key]]
        results = await _execute_tool(step.tool, step.query, _STEP_TOP_K)
        if memo_enabled and results:
            cache_updates[key] = results[0]
        return results

    # A1：deep 档无依赖步骤并行扇出；其余串行
    deep_parallel = parallel_fanout == "deep_only" and state.get("latency_tier") == "deep"
    independent = [s for s in pending if not s.depends_on]
    if deep_parallel and len(independent) > 1:
        batch = await asyncio.gather(*(run_step(s) for s in independent))
        new_results: list[RetrievalResult] = [r for group in batch for r in group]
        executed_ids = {s.step_id for s in independent}
        for s in pending:
            if s.step_id not in executed_ids:
                new_results.extend(await run_step(s))
    else:
        new_results = []
        for s in pending:
            new_results.extend(await run_step(s))

    # fan-in：合并去重 + B3 修剪（checkpoint 写入前）
    prune_cfg = agent_cfg.get("evidence_prune") or {}
    existing = list(state.get("retrieved_evidence") or [])
    merged = dedupe_by_result_id(existing + new_results)
    pruned = prune_evidence(
        merged,
        keep_score=float(prune_cfg.get("keep_score", 0.25)),
        max_content_chars=int(prune_cfg.get("max_content_chars", 600)),
    )

    # 步骤状态置 done + 记忆化合入
    done_plan = [
        s.model_copy(update={"status": "done"}) if s.status != "done" else s
        for s in plan
    ]
    cache.update(cache_updates)

    # E-07：图谱系检索器本轮新增错误 → no-graph（Neo4j/ES 不可达）
    try:
        hub_after = await _get_retriever_hub()
        graph_family_errors_after = sum(
            getattr(hub_after.get(name), "error_count", 0)
            for name in ("graph", "global", "fulltext")
        )
        if graph_family_errors_after > graph_family_errors_before:
            degraded_reasons.append("no-graph")
    except Exception:  # noqa: BLE001 - hub 不可用不阻塞
        pass

    updates: dict[str, Any] = {
        "retrieved_evidence": pruned,
        "tool_call_cache": cache,
        "plan": done_plan,
        "current_step": len(plan),
        "retrieval_rounds": int(state.get("retrieval_rounds", 0)) + 1,
    }
    if degraded_reasons:
        updates["degraded_reasons"] = degraded_reasons
    return updates


# --- 检索器集线器（惰性单例，依赖不可用时抛错由调用方降级） ---
_hub: dict[str, BaseRetriever] | None = None
# M8：集合快照兜底——qdrant 故障时沿用上次枚举结果，hub 不因
# list_collections 失败而不可用（graph 系 error_count 统计保持连续）
_last_collections: list[str] = []


async def _get_retriever_hub() -> dict[str, BaseRetriever]:
    """构建/复用六路检索器集线器（测试可 monkeypatch）。

    C4：客户端与 embedding 服务复用 deps 单例——sparse 通道的
    FlagClient 随 get_embedding_service 一并接入，六路检索不再退化为
    五路；连接池统一由 deps.close_all_clients 管理。
    M8：Dense/Sparse 每次调用按最新集合枚举重建（一次廉价 HTTP），
    admin 重建/新增集合后无需重启即可检索；graph 系检索器实例保持
    复用（error_count 跨轮累积是 E-07 no-graph 判定的依据）。
    C3：集合枚举经 is_business_collection 排除记忆层
    （rag_cache/rag_episodic 的 payload 无 content，混入会产出
    空内容高分配的伪证据）。

    Returns:
        {tool_name: retriever} 字典。

    Raises:
        Exception: 依赖客户端构建失败。
    """
    global _hub, _last_collections

    # 顶层已导入，此处不再惰性导入以避免首个 async 节点内触发 import 阻塞
    import app.api.deps as deps

    qdrant = await deps.shared_qdrant_client()
    es = await deps.shared_es_client()
    neo4j = await deps.shared_neo4j_client()
    embedding = await deps.get_embedding_service()
    try:
        collections = [
            c for c in await qdrant.list_collections() if is_business_collection(c)
        ]
        _last_collections = collections
    except Exception:  # noqa: BLE001 - 枚举失败沿用上次快照（降级）
        collections = _last_collections

    if _hub is None:
        _hub = {
            SourceKind.GRAPH.value: GraphRetriever(neo4j),
            SourceKind.GLOBAL.value: GlobalRetriever(neo4j),
            SourceKind.FULLTEXT.value: FullTextRetriever(es, neo4j),
            SourceKind.WEB.value: WebRetriever(tavily_api_key=None),
        }
    # Dense/Sparse 依赖集合列表，按最新快照重建（薄包装，成本可忽略）
    _hub[SourceKind.DENSE.value] = DenseRetriever(qdrant, embedding, collections)
    _hub[SourceKind.SPARSE.value] = SparseRetriever(qdrant, embedding, collections)
    return _hub
