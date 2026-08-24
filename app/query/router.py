"""
查询理解服务（架构 L2 · M2 合并式结构化调用 · 单元 6.1/6.2）。

v3.1 模块职责收敛（05 §5.1）：本文件是全层唯一 LLM 调用点
（registry query_understanding 角色）——意图/改写/分解/实体一次产出。
decomposer/entity_extractor 已并入合并调用输出 Schema（删除独立类）。

关键行为：
- chitchat 规则前置：零成本启发式（长度/问候语/疑问词，规则表随
  pipeline_config.yaml 热更 J18），命中跳过 LLM（LangSmith 无 span）；
- JSON mode 合并调用；解析失败重试 1 次 → 再失败跳过改写用原始
  查询（D5，X-Degraded 不标记，召回率损失可接受）；
- D4 定档：auto 由本层定档回写实际档位（02 §5，架构 2.4）；
- standard→deep 升级依据 Rerank 置信度（complexity 已废弃）。
"""

# --- 标准库 ---
import json
import logging
from pathlib import Path
from typing import Any

# --- 本地模块 ---
from app.core.models import (
    EntityMention,
    IntentType,
    LatencyTier,
    QueryUnderstandingResult,
)

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "pipeline_config.yaml"

# IntentType 合法值集合（解析校验）
_INTENT_VALUES = {i.value for i in IntentType}

# D4 意图 → 档位矩阵（架构 §2.4 三档策略）
_TIER_MATRIX: dict[str, str] = {
    IntentType.CHITCHAT.value: LatencyTier.FAST.value,
    IntentType.FACTOID.value: LatencyTier.STANDARD.value,
    IntentType.MULTI_HOP.value: LatencyTier.DEEP.value,
    IntentType.COMPARISON.value: LatencyTier.DEEP.value,
    IntentType.GLOBAL_SUMMARY.value: LatencyTier.DEEP.value,
}

_QU_SYSTEM_PROMPT = """你是 GraphRAG 系统的查询理解器。分析用户查询，仅输出 JSON。
输出格式：
{"intent": "factoid|multi_hop|comparison|global_summary|chitchat", "rewritten_query": "改写后的主查询", "subqueries": ["子问题1", "子问题2"], "entities": [{"name": "实体名", "type": "类型"}]}
判定规则：
- factoid：单一事实问答；multi_hop：需多步推理/关系链；comparison：对比多个对象；
- global_summary：总结全局/主题概览类（如"知识库覆盖哪些主题"）；chitchat：闲聊寒暄；
- rewritten_query 保留核心意图、补充关键词、去口语化（已是精确查询则原样返回）；
- subqueries 仅 multi_hop/comparison/global_summary 需要，最多 3 条，其余为空数组；
- 不要输出任何解释文字。"""


def _load_chitchat_rules() -> dict[str, Any]:
    """读取 chitchat 规则表（J18 热更：每次调用现读配置）。

    Returns:
        规则字典（max_length/greeting_words/question_words），缺失用默认。
    """
    defaults: dict[str, Any] = {
        "max_length": 12,
        "greeting_words": ["你好", "您好", "hello", "hi"],
        "question_words": ["怎么做", "如何", "为什么", "是什么"],
    }
    try:
        import yaml

        with open(_CONFIG_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        rules = ((cfg.get("query_understanding") or {}).get("chitchat_rules")) or {}
        return {**defaults, **rules}
    except Exception:  # noqa: BLE001 - 配置缺失用默认
        return defaults


def rule_chitchat(query: str) -> bool:
    """chitchat 规则前置判定（零成本启发式，LLM 调用前执行）。

    规则：问候语表命中即 chitchat；否则长度 ≤ max_length 且不含
    疑问词视为 chitchat。

    Args:
        query: 用户原始查询。

    Returns:
        True 表示规则判定为 chitchat（跳过 LLM 理解调用）。
    """
    rules = _load_chitchat_rules()
    text = query.strip().lower()
    if not text:
        return True
    for word in rules.get("greeting_words") or []:
        if str(word).lower() in text:
            return True
    max_length = int(rules.get("max_length", 12))
    if len(text) > max_length:
        return False
    for word in rules.get("question_words") or []:
        if str(word).lower() in text:
            return False
    return True


def _get_llm() -> Any:
    """获取查询理解 LLM 客户端（query_understanding 角色，测试可替换）。

    Returns:
        LLMClient: 绑定角色条目的客户端。
    """
    from app.llm.registry import get_registry

    return get_registry().for_role("query_understanding")


def _parse_qu_output(content: str) -> QueryUnderstandingResult | None:
    """解析合并调用 JSON 输出（四字段完整性校验）。

    Args:
        content: LLM 输出文本（期望 JSON）。

    Returns:
        QueryUnderstandingResult；解析失败/意图非法返回 None。
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    intent_raw = str(data.get("intent") or "").strip().lower()
    if intent_raw not in _INTENT_VALUES:
        return None
    rewritten = str(data.get("rewritten_query") or "").strip()
    if not rewritten:
        return None
    entities: list[EntityMention] = []
    for item in data.get("entities") or []:
        if isinstance(item, dict) and item.get("name"):
            entities.append(
                EntityMention(name=str(item["name"]), type=str(item.get("type") or ""))
            )
    subqueries = [str(q).strip() for q in (data.get("subqueries") or []) if str(q).strip()]
    return QueryUnderstandingResult(
        intent=IntentType(intent_raw),
        rewritten_query=rewritten,
        subqueries=subqueries[:3],
        entities=entities,
        rule_short_circuit=False,
    )


async def understand_query(
    query: str,
    history_context: str = "",
) -> QueryUnderstandingResult:
    """M2 合并式结构化调用（全层唯一 LLM 调用点）。

    Args:
        query: 用户原始查询。
        history_context: load_memory 注入的多轮上下文（改写前注入）。

    Returns:
        QueryUnderstandingResult；规则短路或 LLM 失败时兜底
        （rewritten_query=原始查询，D5 不标记降级）。
    """
    # chitchat 规则前置：命中跳过 LLM（E-02/S-02：无 query_understanding span）
    if rule_chitchat(query):
        return QueryUnderstandingResult(
            intent=IntentType.CHITCHAT,
            rewritten_query=query,
            rule_short_circuit=True,
        )

    user_prompt = f"用户查询：{query}"
    if history_context:
        user_prompt = f"对话上下文：\n{history_context}\n\n{user_prompt}"

    # 合并调用（解析失败重试 1 次 → 再失败跳过改写用原始查询）
    for attempt in range(2):
        try:
            llm = _get_llm()
            resp = await llm.chat(
                [
                    {"role": "system", "content": _QU_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            result = _parse_qu_output(resp.content)
        except Exception as exc:  # noqa: BLE001 - LLM 失败进入重试/兜底
            logger.warning("query_understanding 调用失败(第%d次): %s", attempt + 1, exc)
            result = None
        if result is not None:
            return result

    logger.warning("query_understanding 重试耗尽，跳过改写用原始查询（D5）")
    return QueryUnderstandingResult(
        intent=IntentType.FACTOID,
        rewritten_query=query,
        rule_short_circuit=False,
    )


def resolve_latency_tier(intent: IntentType, requested_tier: str) -> str:
    """D4 定档：auto 由意图矩阵定档回写，显式档位透传覆盖。

    Args:
        intent: 意图枚举。
        requested_tier: run 入参档位（auto/fast/standard/deep）。

    Returns:
        具体档位（fast/standard/deep）。
    """
    if requested_tier in (t.value for t in LatencyTier):
        return requested_tier
    intent_value = getattr(intent, "value", str(intent))
    return _TIER_MATRIX.get(intent_value, LatencyTier.STANDARD.value)


def should_upgrade_to_deep(
    rerank_scores: list[float],
    rerank_threshold: float,
) -> bool:
    """standard→deep 自动升级判定（v3.1：Rerank 置信度依据）。

    Top-K 精排分普遍低于阈值（均分 < threshold）时升级 deep 重跑。

    Args:
        rerank_scores: Top-K 精排分数列表。
        rerank_threshold: 精排阈值（pipeline_config retrieval.rerank_threshold）。

    Returns:
        True 表示应升级 deep 重跑。
    """
    if not rerank_scores:
        return True  # 无有效证据视为低置信
    avg = sum(rerank_scores) / len(rerank_scores)
    return avg < rerank_threshold
