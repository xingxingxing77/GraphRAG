"""
调试与管道预览端点组（02 §3.11，随关联单元逐个落地）。

当前已落地：POST /admin/debug/embed（向量探针，单元 2.3）。
统一约定同 §3.10：JWT + role=admin；生产可整体禁用
（SYS_403_DEBUG_DISABLED）。
"""

# --- 标准库 ---
import time

# --- 第三方库 ---
from fastapi import APIRouter, Depends

# --- 本地模块 ---
from app.api.deps import get_embedding_service
from app.api.errors import ApiError, ErrorCode
from app.core.models import EmbedProbeRequest, EmbedProbeResponse
from app.embedding.base import EmbeddingService

router = APIRouter()


@router.post("/debug/embed", response_model=EmbedProbeResponse)
async def embed_probe(
    request: EmbedProbeRequest,
    embedding: EmbeddingService = Depends(get_embedding_service),
) -> EmbedProbeResponse:
    """向量探针：输入文本，返回 dense 维数 / sparse 键数 / 耗时。

    Args:
        request: 探针文本。
        embedding: Embedding 服务。

    Returns:
        EmbedProbeResponse: dense_dims / sparse_keys / latency_ms。

    Raises:
        ApiError: SYS_503_DEPENDENCY_DOWN（Ollama/模型服务不可用）。
    """
    # TODO: admin 鉴权 + SYS_403_DEBUG_DISABLED 生产开关（10.2/10.6）
    started = time.perf_counter()
    try:
        result = await embedding.embed([request.text])
    except Exception as exc:  # noqa: BLE001 - 依赖故障统一归因降级
        raise ApiError(
            ErrorCode.SYS_503_DEPENDENCY_DOWN,
            f"Embedding 服务不可用: {exc}",
        ) from exc
    latency_ms = int((time.perf_counter() - started) * 1000)
    dense_dims = len(result.dense[0]) if result.dense else 0
    sparse_keys = len(result.sparse[0]) if result.sparse else 0
    return EmbedProbeResponse(
        dense_dims=dense_dims, sparse_keys=sparse_keys, latency_ms=latency_ms
    )
