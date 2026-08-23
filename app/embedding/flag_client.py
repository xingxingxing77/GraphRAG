"""
FlagEmbedding 进程内封装（架构 §6.2 H1 · 单元 2.3）。

BGE-M3 稀疏向量与 bge-reranker-v2-m3 均经 FlagEmbedding 进程内加载
（J3/H1 定案）。FlagEmbedding 为同步库：调用方必须经
``asyncio.to_thread`` / ``run_in_executor`` 包裹（05 §3.3 铁律 1），
并经全局 semaphore 串行化（铁律 2）。

依赖为可选（pyproject pipeline 组）：未安装时延迟导入抛出明确错误，
不影响其余模块加载。
"""

# --- 标准库 ---
import logging
from typing import Any

logger = logging.getLogger(__name__)


class FlagEmbeddingUnavailable(RuntimeError):
    """FlagEmbedding 依赖或模型不可用（明确错误，便于调用方降级决策）。"""


class FlagClient:
    """FlagEmbedding 进程内封装（同步接口，调用方负责异步包裹）。

    Attributes:
        model_name: BGE-M3 模型标识（HF 仓库名或本地路径）。
        use_fp16: 是否启用 fp16 推理（GPU 可用时）。
    """

    def __init__(self, model_name: str = "BAAI/bge-m3", use_fp16: bool = False) -> None:
        """初始化封装（惰性加载模型）。

        Args:
            model_name: BGE-M3 模型标识。
            use_fp16: 是否 fp16 推理。
        """
        self.model_name = model_name
        self.use_fp16 = use_fp16
        self._model: Any = None

    def _ensure_model(self) -> Any:
        """惰性加载 BGEM3FlagModel（未安装依赖时抛明确错误）。

        Returns:
            已加载的模型实例。

        Raises:
            FlagEmbeddingUnavailable: 依赖未安装或模型加载失败。
        """
        if self._model is not None:
            return self._model
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:
            raise FlagEmbeddingUnavailable(
                "FlagEmbedding 未安装（pyproject pipeline 可选组）"
            ) from exc
        try:
            self._model = BGEM3FlagModel(self.model_name, use_fp16=self.use_fp16)
        except Exception as exc:  # noqa: BLE001 - 模型加载失败统一归因
            raise FlagEmbeddingUnavailable(f"BGE-M3 模型加载失败: {exc}") from exc
        return self._model

    def encode_sparse(self, texts: list[str]) -> list[dict[int, float]]:
        """同步生成稀疏向量（调用方须经 executor 包裹）。

        Args:
            texts: 输入文本列表。

        Returns:
            稀疏向量列表，每项 {token_id: weight}。

        Raises:
            FlagEmbeddingUnavailable: 依赖/模型不可用。
        """
        model = self._ensure_model()
        output = model.encode(texts, return_dense=False, return_sparse=True)
        sparse_dicts: list[dict[int, float]] = []
        for item in output["lexical_weights"]:
            sparse_dicts.append({int(k): float(v) for k, v in item.items()})
        return sparse_dicts
