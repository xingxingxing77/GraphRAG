"""
Prometheus 指标暴露端点（架构第 10 层 · 05 §7 · 单元 3.6）。

GET /metrics —— Prometheus 抓取端点（服务根路径，与 /health 同级）。
"""

# --- 第三方库 ---
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus 指标抓取端点。

    Returns:
        Response: text/plain 格式的指标文本（OpenMetrics 兼容）。
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
