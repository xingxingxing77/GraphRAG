"""
多路检索结果融合器（架构 L4 · 单元 3.5）。

RRF（k=60 排名融合）与加权融合双模式；策略与权重取自
config/pipeline_config.yaml（retrieval.fusion / weights）。
融合前各路先 min-max 归一化；跨路同文档按 chunk_id/内容哈希合并，
输出 Top-N（默认 20）送精排。
"""

# --- 标准库 ---
import hashlib
import logging
from pathlib import Path

# --- 本地模块 ---
from app.core.models import RetrievalResult
from app.retrieval.normalizer import ScoreNormalizer

logger = logging.getLogger(__name__)

# 融合配置来源（pipeline_config.yaml）
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "pipeline_config.yaml"

# 默认权重（与 pipeline_config.yaml weights 对齐）
_DEFAULT_WEIGHTS: dict[str, float] = {
    "dense": 0.4,
    "sparse": 0.2,
    "graph": 0.3,
    "global": 0.2,
    "fulltext": 0.2,
    "web": 0.1,
}


def _load_config() -> tuple[str, dict[str, float]]:
    """从 pipeline_config.yaml 读取融合策略与权重（失败用默认）。

    Returns:
        (strategy, weights)：strategy ∈ {"rrf", "weighted"}。
    """
    try:
        import yaml

        with open(_CONFIG_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        retrieval_cfg = cfg.get("retrieval") or {}
        strategy = str(retrieval_cfg.get("fusion", "rrf"))
        raw_weights = retrieval_cfg.get("weights") or cfg.get("weights") or _DEFAULT_WEIGHTS
        # 合并默认值：YAML缺失的路自动补齐（P0-05），避免 weighted 静默禁用
        merged = dict(_DEFAULT_WEIGHTS)
        for k, v in dict(raw_weights).items():
            merged[str(k)] = float(v)
        # 归一化：和为1，消除配置增减导致的分数漂移
        total = sum(merged.values())
        if total > 1e-12:
            merged = {k: v / total for k, v in merged.items()}
        return strategy, merged
    except Exception as exc:  # noqa: BLE001 - 配置缺失用默认
        logger.warning("融合配置读取失败，使用默认: %s", exc)
        total = sum(_DEFAULT_WEIGHTS.values())
        norm = {k: v / total for k, v in _DEFAULT_WEIGHTS.items()} if total > 1e-12 else dict(_DEFAULT_WEIGHTS)
        return "rrf", norm


def _doc_key(result: RetrievalResult) -> str:
    """计算跨路文档合并键（chunk_id 优先，回退内容哈希）。

    Args:
        result: 检索结果。

    Returns:
        文档身份键。
    """
    if result.chunk_id:
        return f"chunk:{result.chunk_id}"
    # P1 M-18: 延长至24位（96bit）降低万级碰撞概率
    return "content:" + hashlib.sha256(result.content.encode("utf-8")).hexdigest()[:24]


class FusionEngine:
    """检索结果融合引擎。

    Attributes:
        strategy: 融合策略（rrf | weighted）。
        weights: 各路权重（weighted 模式）。
        rrf_k: RRF 常数 k（默认 60）。
    """

    def __init__(
        self,
        strategy: str | None = None,
        weights: dict[str, float] | None = None,
        rrf_k: int = 60,
    ) -> None:
        """初始化融合引擎（缺省从 pipeline_config.yaml 读取）。

        Args:
            strategy: 融合策略，None 时读配置。
            weights: 各路权重，None 时读配置。
            rrf_k: RRF 算法常数 k（默认 60）。
        """
        cfg_strategy, cfg_weights = _load_config()
        self.strategy = strategy or cfg_strategy
        # weights 显式传入时同样归一化（P0-05）
        raw = weights if weights is not None else cfg_weights
        if weights is not None:
            merged = dict(cfg_weights)
            merged.update({str(k): float(v) for k, v in weights.items()})
            total = sum(merged.values())
            raw = {k: v / total for k, v in merged.items()} if total > 1e-12 else merged
        self.weights = raw
        self.rrf_k = rrf_k

    def fuse(
        self,
        results_by_source: dict[str, list[RetrievalResult]],
        top_n: int = 20,
    ) -> list[RetrievalResult]:
        """融合多路检索结果（Top-N 输出送精排）。

        Args:
            results_by_source: 按来源分组的检索结果。
            top_n: 融合后保留的数量（架构：Top-20）。

        Returns:
            融合排序后的结果列表。
        """
        if self.strategy == "weighted":
            return self._weighted_fusion(results_by_source, top_n)
        return self._rrf_fusion(results_by_source, top_n)

    def _rrf_fusion(
        self,
        results_by_source: dict[str, list[RetrievalResult]],
        top_n: int,
    ) -> list[RetrievalResult]:
        """Reciprocal Rank Fusion：score(d) = Σ_i 1/(k + rank_i(d))。

        Args:
            results_by_source: 按来源分组的结果（各路已按分数降序）。
            top_n: 保留数量。

        Returns:
            RRF 排序后的结果（跨路同文档合并，分数为 RRF 累计）。
        """
        accumulated: dict[str, float] = {}
        representative: dict[str, RetrievalResult] = {}
        for _source, results in results_by_source.items():
            for rank, result in enumerate(results, start=1):
                key = _doc_key(result)
                accumulated[key] = accumulated.get(key, 0.0) + 1.0 / (
                    self.rrf_k + rank
                )
                # 代表条目保留分数最高者
                current = representative.get(key)
                if current is None or result.score > current.score:
                    representative[key] = result
        ordered = sorted(accumulated.items(), key=lambda kv: -kv[1])
        # M2：RRF 累计分上限 ≈ 6/(k+1) ≈ 0.098，与下游 0-1 阈值口径
        # （B3 修剪/A2 短路）不可比 → 按本批最大 RRF 归一化到 [0,1]，
        # 原始累计分保留在 metadata["rrf"]
        max_rrf = ordered[0][1] if ordered else 0.0
        fused: list[RetrievalResult] = []
        for key, score in ordered[:top_n]:
            rep = representative[key]
            meta = dict(rep.metadata or {})
            meta["rrf"] = score
            norm = score / max_rrf if max_rrf > 0 else 0.0
            fused.append(rep.model_copy(update={"score": norm, "metadata": meta}))
        return fused

    def _weighted_fusion(
        self,
        results_by_source: dict[str, list[RetrievalResult]],
        top_n: int,
    ) -> list[RetrievalResult]:
        """加权融合：score(d) = Σ_i weight_i × norm_score_i(d)。

        各路先 min-max 归一化到 [0,1] 再加权求和。

        Args:
            results_by_source: 按来源分组的结果。
            top_n: 保留数量。

        Returns:
            加权排序后的结果（跨路同文档合并）。
        """
        accumulated: dict[str, float] = {}
        representative: dict[str, RetrievalResult] = {}
        for source, results in results_by_source.items():
            weight = self.weights.get(source, 0.0)
            normalized = ScoreNormalizer.min_max_normalize(results)
            for result in normalized:
                key = _doc_key(result)
                accumulated[key] = accumulated.get(key, 0.0) + weight * result.score
                current = representative.get(key)
                if current is None or result.score > current.score:
                    representative[key] = result
        ordered = sorted(accumulated.items(), key=lambda kv: -kv[1])
        return [
            representative[key].model_copy(update={"score": score})
            for key, score in ordered[:top_n]
        ]
