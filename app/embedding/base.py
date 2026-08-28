"""
Embedding 统一接口协议（架构 §3.5 + §6.2）。

实现约束（05 §3.3 async 三铁律）：
- 同步推理必须 run_in_executor 包裹
- GPU 推理经全局 semaphore 串行化
- 外部调用必有独立超时（reliability.yaml）

Embedding/Reranker 不进 models.yaml 注册表（J3）：固定本地
BGE-M3 + bge-reranker-v2-m3。
"""

# --- 标准库 ---
from typing import Protocol, runtime_checkable

# --- 本地模块 ---
from app.core.models import EmbeddingResult


@runtime_checkable
class EmbeddingService(Protocol):
    """向量化服务协议（BGE-M3 双通道：dense 1024 维 + sparse）。"""

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """对文本列表向量化，同时返回密集与稀疏向量。

        Args:
            texts: 待向量化的文本列表。

        Returns:
            EmbeddingResult: dense shape (n, 1024) + sparse {token_id: weight}。
        """
        ...

    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        """仅获取密集向量（M7：dense-only 消费方专用，免跑稀疏编码）。

        Args:
            texts: 待向量化的文本列表。

        Returns:
            密集向量列表，shape (n, 1024)。
        """
        ...
