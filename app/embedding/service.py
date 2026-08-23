"""
BGE-M3 统一 Embedding 服务（架构 §6.2 · 单元 2.3）。

双通道：dense（Ollama embed API）+ sparse（FlagEmbedding 进程内）。
async 三铁律集成（05 §3.3）：
1. FlagEmbedding 同步推理经 ``asyncio.to_thread`` 包裹；
2. GPU 推理经全局 semaphore 串行化（bulkhead）；
3. 外部调用独立超时（reliability.yaml timeouts_seconds.embedding）。

FlagEmbedding 未接入时 sparse 返回空并告警（不阻塞 dense 通道，
稀疏检索能力随 pipeline 可选组安装后自动恢复）。
"""

# --- 标准库 ---
import asyncio
import logging

# --- 本地模块 ---
from app.core.models import EmbeddingResult
from app.embedding.flag_client import FlagClient, FlagEmbeddingUnavailable
from app.embedding.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

# 默认独立超时（reliability.yaml timeouts_seconds.embedding）
_DEFAULT_EMBED_TIMEOUT = 5.0


class BgeM3EmbeddingService:
    """统一的 BGE-M3 Embedding 服务（EmbeddingService 协议实现）。

    Attributes:
        ollama_client: Ollama API 客户端（dense 通道）。
        model_name: Embedding 模型名称。
        flag_client: FlagEmbedding 封装（sparse 通道，可选）。
        timeout: 单通道独立超时（秒）。
    """

    def __init__(
        self,
        ollama_client: OllamaClient,
        model_name: str = "bge-m3",
        flag_client: FlagClient | None = None,
        timeout: float = _DEFAULT_EMBED_TIMEOUT,
        semaphore_limit: int = 1,
    ) -> None:
        """初始化 Embedding 服务。

        Args:
            ollama_client: Ollama API 客户端。
            model_name: Embedding 模型名称。
            flag_client: FlagEmbedding 封装（None 时 sparse 通道降级为空）。
            timeout: 单通道独立超时（秒）。
            semaphore_limit: GPU 推理并发上限（bulkhead，默认串行）。
        """
        self.ollama_client = ollama_client
        self.model_name = model_name
        self.flag_client = flag_client
        self.timeout = timeout
        # 全局 semaphore：GPU 推理串行化（05 §3.3 铁律 2）
        self._semaphore = asyncio.Semaphore(semaphore_limit)

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """对文本列表向量化，同时返回密集向量和稀疏向量。

        双通道均经 semaphore 串行与独立超时保护。

        Args:
            texts: 待向量化的文本列表。

        Returns:
            EmbeddingResult: dense shape (n, 1024) + sparse {token_id: weight}。

        Raises:
            asyncio.TimeoutError: dense 通道超时（调用方决定降级策略）。
        """
        async with self._semaphore:
            dense = await asyncio.wait_for(self._dense(texts), timeout=self.timeout)
            sparse = await self._sparse(texts)
        return EmbeddingResult(dense=dense, sparse=sparse)

    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        """仅获取密集向量（经 semaphore 与超时保护）。

        Args:
            texts: 文本列表。

        Returns:
            密集向量列表，shape (n, 1024)。
        """
        async with self._semaphore:
            return await asyncio.wait_for(self._dense(texts), timeout=self.timeout)

    async def embed_sparse(self, texts: list[str]) -> list[dict[int, float]]:
        """仅获取稀疏向量（FlagEmbedding 同步推理经 to_thread 包裹）。

        Args:
            texts: 文本列表。

        Returns:
            稀疏向量列表（FlagEmbedding 未接入时为空列表）。
        """
        async with self._semaphore:
            return await self._sparse(texts)

    async def embed_query(self, query: str) -> EmbeddingResult:
        """对单条查询进行向量化。

        Args:
            query: 查询文本。

        Returns:
            EmbeddingResult: 单条查询的向量结果。
        """
        return await self.embed([query])

    async def _dense(self, texts: list[str]) -> list[list[float]]:
        """dense 通道：Ollama embed API。

        Args:
            texts: 文本列表。

        Returns:
            密集向量列表。
        """
        return await self.ollama_client.embed(self.model_name, texts)

    async def _sparse(self, texts: list[str]) -> list[dict[int, float]]:
        """sparse 通道：FlagEmbedding 进程内（同步推理经 to_thread 包裹）。

        Args:
            texts: 文本列表。

        Returns:
            稀疏向量列表（依赖未接入时降级为空并告警）。
        """
        if self.flag_client is None:
            logger.warning("FlagEmbedding 未接入，sparse 通道降级为空（dense-only）")
            return [{} for _ in texts]
        try:
            # 铁律 1：同步推理必须经 executor 包裹，避免阻塞事件循环
            return await asyncio.to_thread(self.flag_client.encode_sparse, texts)
        except FlagEmbeddingUnavailable as exc:
            logger.warning("sparse 通道不可用，降级为空: %s", exc)
            return [{} for _ in texts]
