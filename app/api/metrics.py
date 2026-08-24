"""
Prometheus 指标定义（架构第 10 层 · 05 §7 · 单元 3.6）。

五项指标（05 §7）：
- rag_request_duration_seconds{tier,intent}：请求耗时直方图；
- rag_retrieval_errors_total{source}：检索失败计数（按来源）；
- rag_llm_tokens_total{role,model}：Token 用量累计；
- rag_degraded_total{reason}：降级触发计数（按原因）；
- rag_agent_rounds{tier}：Agent 回环轮次直方图。
"""

# --- 第三方库 ---
from prometheus_client import Counter, Histogram

# 请求耗时直方图（tier: fast/standard/deep/auto；intent: 查询意图）
REQUEST_DURATION = Histogram(
    "rag_request_duration_seconds",
    "端到端请求耗时（秒）",
    ["tier", "intent"],
    buckets=(0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0),
)

# 检索失败计数（source: dense/sparse/graph/global/fulltext/web）
RETRIEVAL_ERRORS = Counter(
    "rag_retrieval_errors_total",
    "检索失败次数（按来源）",
    ["source"],
)

# LLM Token 用量（role: prompt/completion；model: 模型名）
LLM_TOKENS = Counter(
    "rag_llm_tokens_total",
    "LLM Token 用量（按角色与模型）",
    ["role", "model"],
)

# 降级触发计数（reason: 02 §2.4 七枚举）
DEGRADED_TOTAL = Counter(
    "rag_degraded_total",
    "降级触发次数（按原因）",
    ["reason"],
)

# Agent 回环轮次直方图（tier 分档）
AGENT_ROUNDS = Histogram(
    "rag_agent_rounds",
    "Agent reflector→planner 回环轮次",
    ["tier"],
    buckets=(1, 2, 3, 4, 5),
)


def record_retrieval_error(source: str, count: int = 1) -> None:
    """上报检索失败计数。

    Args:
        source: 检索来源（SourceKind 值）。
        count: 失败次数。
    """
    if count > 0:
        RETRIEVAL_ERRORS.labels(source=source).inc(count)


def record_degraded(reason: str) -> None:
    """上报一次降级触发。

    Args:
        reason: 降级原因（02 §2.4 枚举值）。
    """
    DEGRADED_TOTAL.labels(reason=reason).inc()


def record_llm_tokens(role: str, model: str, tokens: int) -> None:
    """上报 LLM Token 用量。

    Args:
        role: prompt | completion。
        model: 模型名。
        tokens: Token 数。
    """
    if tokens > 0:
        LLM_TOKENS.labels(role=role, model=model).inc(tokens)


def _init_label_series() -> None:
    """预初始化代表性标签序列（保证 /metrics 五项指标族恒可见）。"""
    REQUEST_DURATION.labels(tier="auto", intent="query")
    for source in ("dense", "sparse", "graph", "global", "fulltext", "web"):
        RETRIEVAL_ERRORS.labels(source=source)
    LLM_TOKENS.labels(role="prompt", model="unknown")
    LLM_TOKENS.labels(role="completion", model="unknown")
    for reason in (
        "no-graph",
        "no-rerank",
        "llm-fallback",
        "no-memory",
        "no-cache",
        "budget-exhausted",
        "no-persistence",
    ):
        DEGRADED_TOTAL.labels(reason=reason)
    AGENT_ROUNDS.labels(tier="auto")


_init_label_series()
