"""
BGE-M3 统一 Embedding 服务。

同时产出密集向量和稀疏向量，封装为统一接口。
"""

# --- 标准库 ---
from dataclasses import dataclass
from typing import Optional

# --- 本地模块 ---
from app.embedding.ollama_client import OllamaClient


@dataclass
class EmbeddingResult:
    """Embedding 结果。

    Attributes:
        dense: 密集向量列表，shape: (n, 1024)。
        sparse: 稀疏向量列表，每项为 {token_id: weight}。
    """

    dense: list[list[float]]
    sparse: list[dict[int, float]]


class EmbeddingService:
    """统一的 BGE-M3 Embedding 服务。

    通过 Ollama 调用 BGE-M3 模型，同时产出密集向量和稀疏向量。
    """

    def __init__(
        self,
        ollama_client: OllamaClient,
        model_name: str = "bge-m3",
    ) -> None:
        """初始化 Embedding 服务。

        Args:
            ollama_client: Ollama API 客户端。
            model_name: Embedding 模型名称。
        """
        self.ollama_client = ollama_client
        self.model_name = model_name

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """对文本列表进行向量化，同时返回密集和稀疏向量。

        Args:
            texts: 待向量化的文本列表。

        Returns:
            EmbeddingResult: 包含密集向量和稀疏向量。
        """
        # TODO: 调用 Ollama 获取密集向量
        # TODO: 通过 FlagEmbedding 或独立服务获取稀疏向量
        # TODO: 组装并返回 EmbeddingResult
        raise NotImplementedError

    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        """仅获取密集向量。

        Args:
            texts: 文本列表。

        Returns:
            密集向量列表，shape: (n, 1024)。
        """
        # TODO: 调用 Ollama embed API
        raise NotImplementedError

    async def embed_sparse(self, texts: list[str]) -> list[dict[int, float]]:
        """仅获取稀疏向量。

        Args:
            texts: 文本列表。

        Returns:
            稀疏向量列表，每项为 {token_id: weight}。
        """
        # TODO: 通过 FlagEmbedding 库计算稀疏向量
        raise NotImplementedError

    async def embed_query(self, query: str) -> EmbeddingResult:
        """对单条查询进行向量化。

        Args:
            query: 查询文本。

        Returns:
            EmbeddingResult: 单条查询的向量结果。
        """
        result = await self.embed([query])
        return EmbeddingResult(
            dense=result.dense[0] if result.dense else [],
            sparse=result.sparse[0] if result.sparse else {},
        )
