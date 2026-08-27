"""
BGE-Reranker 精排器（架构 §6.2 H1 · 05 §3.3 · 单元 4.1）。

bge-reranker-v2-m3 Cross-Encoder 经 FlagEmbedding 进程内加载，
严格遵循 async 三铁律：
1. 同步推理 run_in_executor 包裹（不阻塞事件循环）；
2. 全局 semaphore 串行化（bulkhead，reliability.yaml = 1）；
3. 独立超时 2s（timeouts_seconds.reranker），超时/不可用走
   no-rerank 降级：返回原序粗排分数（D5，X-Degraded: no-rerank，E-08）。
"""

# --- 标准库 ---
import asyncio
import logging
from typing import Any, Callable, Optional

# --- 本地模块 ---
from app.api.metrics import record_degraded
from app.core.models import RetrievalResult
from app.reranking.base import RerankerService

logger = logging.getLogger(__name__)

# 全局 semaphore（铁律 2：与 LLM 共享显存，串行化 bulkhead）
_RERANK_SEM = asyncio.Semaphore(1)

# 独立超时（reliability.yaml timeouts_seconds.reranker）
_RERANK_TIMEOUT_S = 2.0


class BGEReranker(RerankerService):
    """BGE-Reranker 精排器（Cross-Encoder 查询-文档对打分）。

    Attributes:
        model_name: Reranker 模型标识（HF 仓库名或本地路径）。
        degraded_count: 降级次数计数（可观测数据源）。
        last_degraded: 最近一次调用是否降级（调试端点回显）。
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        timeout_s: float = _RERANK_TIMEOUT_S,
        score_fn: Optional[Callable[[list[list[str]]], list[float]]] = None,
    ) -> None:
        """初始化 Reranker（模型惰性加载）。

        Args:
            model_name: Reranker 模型标识。
            timeout_s: 独立超时（秒），超时走 no-rerank 降级。
            score_fn: 注入的同步打分函数（测试替身），签名
                pairs -> scores；为 None 时走 FlagEmbedding。
        """
        self.model_name = model_name
        self.timeout_s = timeout_s
        self._score_fn = score_fn
        self._model: Any = None
        self.degraded_count = 0
        self.last_degraded = False

    async def rerank(
        self,
        query: str,
        docs: list[RetrievalResult],
        top_k: int,
    ) -> list[tuple[RetrievalResult, float]]:
        """对候选证据精排（超时/不可用降级粗排原序）。

        Args:
            query: 查询文本。
            docs: 融合层粗排 Top-N 候选。
            top_k: 精排后保留数量。

        Returns:
            (结果, 精排分) 列表，按精排分降序，长度 ≤ top_k；
            降级时返回原序粗排分数。
        """
        self.last_degraded = False
        if not docs:
            return []
        pairs = [[query, d.content] for d in docs]
        async with _RERANK_SEM:
            try:
                scores = await asyncio.wait_for(
                    self._score(pairs), timeout=self.timeout_s
                )
            except Exception as exc:  # noqa: BLE001 - 含超时，D5 降级
                logger.warning("rerank 降级（no-rerank）: %s", exc)
                return self._degrade(docs, top_k)
        ranked = sorted(zip(docs, scores), key=lambda x: -x[1])
        return ranked[:top_k]

    # 单次推理最大批量，防止 OOM（P2-04）
    _MAX_BATCH = 32

    async def _score(self, pairs: list[list[str]]) -> list[float]:
        """打分调度（铁律 1：同步推理经 executor 包裹，分批防 OOM）。

        Args:
            pairs: [[query, passage], ...] 对列表。

        Returns:
            每对的相关性分数。
        """
        if len(pairs) > self._MAX_BATCH:
            # 分批累积
            scores: list[float] = []
            for i in range(0, len(pairs), self._MAX_BATCH):
                chunk = pairs[i : i + self._MAX_BATCH]
                if self._score_fn is not None:
                    chunk_scores = [float(s) for s in await asyncio.to_thread(self._score_fn, chunk)]
                else:
                    loop = asyncio.get_running_loop()
                    chunk_scores = await loop.run_in_executor(None, self._score_sync, chunk)
                scores.extend(chunk_scores)
            return scores
        if self._score_fn is not None:
            return [float(s) for s in await asyncio.to_thread(self._score_fn, pairs)]
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._score_sync, pairs)

    def _score_sync(self, pairs: list[list[str]]) -> list[float]:
        """FlagEmbedding 同步打分（executor 线程内执行）。

        Args:
            pairs: [[query, passage], ...] 对列表。

        Returns:
            归一化后的相关性分数（sigmoid，[0,1]）。

        Raises:
            RuntimeError: FlagEmbedding 未安装或模型加载失败。
        """
        model = self._ensure_model()
        raw = model.compute_score(pairs, normalize=True)
        if isinstance(raw, (int, float)):
            raw = [raw]
        return [float(s) for s in raw]

    def _ensure_model(self) -> Any:
        """惰性加载 FlagReranker（依赖缺失抛明确错误供降级决策）。

        Returns:
            已加载的 FlagReranker 实例。

        Raises:
            RuntimeError: 依赖未安装或模型加载失败。
        """
        if self._model is not None:
            return self._model
        try:
            from FlagEmbedding import FlagReranker  # 延迟导入（可选依赖）
        except ImportError as exc:
            raise RuntimeError("FlagEmbedding 未安装（pyproject pipeline 可选组）") from exc
        try:
            self._model = FlagReranker(self.model_name, use_fp16=False)
        except Exception as exc:  # noqa: BLE001 - 模型加载失败统一归因
            raise RuntimeError(f"Reranker 模型加载失败: {exc}") from exc
        return self._model

    def _degrade(
        self, docs: list[RetrievalResult], top_k: int
    ) -> list[tuple[RetrievalResult, float]]:
        """no-rerank 降级：返回原序粗排分数（D5，E-08）。

        Args:
            docs: 粗排候选。
            top_k: 保留数量。

        Returns:
            (结果, 粗排分) 列表，原序截断。
        """
        self.degraded_count += 1
        self.last_degraded = True
        record_degraded("no-rerank")
        return [(d, d.score) for d in docs[:top_k]]
