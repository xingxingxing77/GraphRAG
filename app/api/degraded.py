"""
X-Degraded 透传链（架构 D5 · 02 §2.4 · 单元 9.1）。

图内各降级点经 AgentState.degraded_reasons 上报（并集去重 reducer），
values 终态经本模块校验后透传为 HTTP 响应头 X-Degraded（逗号分隔）。
枚举以 02 §2.4 为唯一权威；未知值剔除并告警（防契约漂移）。
"""

# --- 标准库 ---
import logging
from typing import Any

# --- 第三方库 ---
from fastapi import Response

logger = logging.getLogger(__name__)

# 02 §2.4 权威七值（doc-lint R1 双向校验同源）
CANONICAL_DEGRADED_REASONS: tuple[str, ...] = (
    "no-graph",
    "no-rerank",
    "llm-fallback",
    "no-memory",
    "no-cache",
    "budget-exhausted",
    "no-persistence",
)

# 响应头名（02 §2.4；CORS expose_headers 已放行）
X_DEGRADED_HEADER = "X-Degraded"


def build_degraded_header(reasons: list[str] | None) -> str | None:
    """校验并组装 X-Degraded 头值。

    Args:
        reasons: 图内上报的降级原因列表（values 终态 degraded_reasons）。

    Returns:
        逗号分隔的合法枚举值；无降级返回 None（不下发头）。
    """
    if not reasons:
        return None
    valid: list[str] = []
    for reason in reasons:
        if reason in CANONICAL_DEGRADED_REASONS:
            if reason not in valid:
                valid.append(reason)
        else:
            logger.warning("剔除未登记降级值: %s（02 §2.4 权威表外）", reason)
    return ",".join(valid) if valid else None


def apply_degraded_header(response: Response, reasons: list[str] | None) -> Response:
    """将降级原因写入响应头（有降级才下发）。

    Args:
        response: FastAPI 响应对象。
        reasons: 降级原因列表。

    Returns:
        原响应对象（就地设置头）。
    """
    header_value = build_degraded_header(reasons)
    if header_value is not None:
        response.headers[X_DEGRADED_HEADER] = header_value
    return response


def reasons_from_values(values_state: dict[str, Any]) -> list[str]:
    """从图 values 终态提取降级原因（10.3 SSE 接线消费入口）。

    Args:
        values_state: langgraph values 事件的状态字典。

    Returns:
        降级原因列表（可能为空）。
    """
    reasons = values_state.get("degraded_reasons") or []
    return [str(r) for r in reasons]
