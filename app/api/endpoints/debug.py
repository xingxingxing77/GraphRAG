"""
调试与管道预览端点组（02 §3.11，随关联单元逐个落地）。

当前已落地：POST /admin/debug/embed（向量探针，单元 2.3）、
POST /admin/debug/analyze（IK 分词调试，单元 3.2）、
POST /admin/debug/retrieve（六路检索 + 融合，单元 3.3-3.5）。
统一约定同 §3.10：JWT + role=admin；生产可整体禁用
（SYS_403_DEBUG_DISABLED）。
"""

# --- 标准库 ---
import time

# --- 第三方库 ---
from fastapi import APIRouter, Depends

# --- 本地模块 ---
from app.api.deps import (
    get_embedding_service,
    get_es_client,
    get_neo4j_client,
    get_qdrant_client,
    get_reranker,
)
from app.api.errors import ApiError, ErrorCode
from app.api.metrics import record_retrieval_error
from app.core.models import (
    DebugRerankRankedItem,
    DebugRerankRequest,
    DebugRerankResponse,
    DebugRetrieveRequest,
    DebugRetrieveResponse,
    EmbedProbeRequest,
    EmbedProbeResponse,
    IkAnalyzeRequest,
    IkAnalyzeResponse,
    RetrievalResult,
    SourceKind,
)
from app.db.es_client import ESClient
from app.db.neo4j_client import Neo4jClient
from app.db.qdrant_client import QdrantDBClient
from app.embedding.base import EmbeddingService
from app.retrieval.base import BaseRetriever
from app.retrieval.dense_retriever import DenseRetriever
from app.retrieval.deduplicator import Deduplicator
from app.retrieval.fulltext_retriever import FullTextRetriever
from app.retrieval.fusion import FusionEngine
from app.retrieval.global_retriever import GlobalRetriever
from app.retrieval.graph_retriever import GraphRetriever
from app.retrieval.sparse_retriever import SparseRetriever
from app.retrieval.web_retriever import WebRetriever
from app.reranking.reranker import BGEReranker

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


@router.post("/debug/analyze", response_model=IkAnalyzeResponse)
async def ik_analyze(
    request: IkAnalyzeRequest,
    es: ESClient = Depends(get_es_client),
) -> IkAnalyzeResponse:
    """IK 分词调试（封装 _analyze API）。

    Args:
        request: 目标索引 + 待分词文本。
        es: ES 客户端。

    Returns:
        IkAnalyzeResponse: 分词 token 列表。

    Raises:
        ApiError: GRAPH_503_STORE_UNAVAILABLE（ES 不可用）。
    """
    # TODO: admin 鉴权（10.2）
    try:
        await es.ensure_indices()
        tokens = await es.analyze(request.index, request.text, analyzer="ik_smart")
    except Exception as exc:  # noqa: BLE001 - ES 不可用归因降级
        raise ApiError(
            ErrorCode.GRAPH_503_STORE_UNAVAILABLE, f"ES 分词失败: {exc}"
        ) from exc
    return IkAnalyzeResponse(tokens=tokens)


@router.post("/debug/retrieve", response_model=DebugRetrieveResponse)
async def debug_retrieve(
    request: DebugRetrieveRequest,
    qdrant: QdrantDBClient = Depends(get_qdrant_client),
    neo4j: Neo4jClient = Depends(get_neo4j_client),
    es: ESClient = Depends(get_es_client),
    embedding: EmbeddingService = Depends(get_embedding_service),
) -> DebugRetrieveResponse:
    """六路检索调试（sources 过滤 + 分组返回 + 融合 Top-N，单元 3.5）。

    六路：dense/sparse/graph/global/fulltext/web；fused 为融合三件套
    （去重 → RRF/加权融合）输出 Top-20。单路失败不阻塞其余路。

    Args:
        request: 查询 + top_k + sources 过滤。
        qdrant: Qdrant 客户端。
        neo4j: Neo4j 客户端。
        es: ES 客户端。
        embedding: Embedding 服务。

    Returns:
        DebugRetrieveResponse: 按源分组结果 + fused（当前为空）。

    Raises:
        ApiError: DEBUG_400_INVALID_SOURCE（sources 含非法源）。
    """
    # TODO: admin 鉴权（10.2）
    all_sources = set(SourceKind)
    requested = set(request.sources) if request.sources else all_sources
    unsupported = requested - all_sources
    if unsupported:
        raise ApiError(
            ErrorCode.DEBUG_400_INVALID_SOURCE,
            f"非法检索源: {[s.value for s in unsupported]}",
        )

    collections = [c for c in await qdrant.list_collections() if c.startswith("rag_")]
    results: dict[str, list[RetrievalResult]] = {}
    retrievers: list[BaseRetriever] = []
    if SourceKind.DENSE in requested:
        r: BaseRetriever = DenseRetriever(qdrant, embedding, collections)
        retrievers.append(r)
        results[SourceKind.DENSE.value] = await r.retrieve(request.query, request.top_k)
    if SourceKind.SPARSE in requested:
        r = SparseRetriever(qdrant, embedding, collections)
        retrievers.append(r)
        results[SourceKind.SPARSE.value] = await r.retrieve(request.query, request.top_k)
    if SourceKind.GRAPH in requested:
        r = GraphRetriever(neo4j)
        retrievers.append(r)
        results[SourceKind.GRAPH.value] = await r.retrieve(request.query, request.top_k)
    if SourceKind.GLOBAL in requested:
        r = GlobalRetriever(neo4j)
        retrievers.append(r)
        results[SourceKind.GLOBAL.value] = await r.retrieve(request.query, request.top_k)
    if SourceKind.FULLTEXT in requested:
        r = FullTextRetriever(es, neo4j)
        retrievers.append(r)
        results[SourceKind.FULLTEXT.value] = await r.retrieve(request.query, request.top_k)
    if SourceKind.WEB in requested:
        r = WebRetriever()
        retrievers.append(r)
        results[SourceKind.WEB.value] = await r.retrieve(request.query, request.top_k)

    # 可观测接入（单元 3.6）：检索器错误计数 → rag_retrieval_errors_total
    for retriever in retrievers:
        record_retrieval_error(retriever.name.value, retriever.error_count)

    # 融合三件套（单元 3.5）：去重（result_id）→ 融合 Top-20 送精排口径
    fused_results = FusionEngine().fuse(results, top_n=20)
    fused_results = Deduplicator.deduplicate(fused_results, strategy="result_id")
    fused = [{"result_id": r.result_id, "content": r.content} for r in fused_results]
    return DebugRetrieveResponse(results=results, fused=fused)


@router.post("/debug/rerank", response_model=DebugRerankResponse)
async def debug_rerank(
    request: DebugRerankRequest,
    reranker: BGEReranker = Depends(get_reranker),
) -> DebugRerankResponse:
    """精排对比调试（02 §3.11，单元 4.1）。

    FlagEmbedding 未安装/超时时自动 no-rerank 降级（degraded=true）。

    Args:
        request: 查询 + 候选文档 + top_k。
        reranker: 精排器单例。

    Returns:
        DebugRerankResponse: 精排后列表 + 降级标志 + 耗时。
    """
    # TODO: admin 鉴权（10.2）
    docs = [
        RetrievalResult(
            result_id=f"debug:{i}",
            chunk_id=None,
            content=d.content,
            score=1.0 - i * 0.01,  # 粗排序占位分（输入顺序）
            source=SourceKind.DENSE,
            doc_id=None,
            metadata={},
        )
        for i, d in enumerate(request.docs)
    ]
    start = time.perf_counter()
    ranked = await reranker.rerank(request.query, docs, request.top_k)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return DebugRerankResponse(
        ranked=[DebugRerankRankedItem(content=d.content, score=s) for d, s in ranked],
        degraded=reranker.last_degraded,
        elapsed_ms=elapsed_ms,
    )
