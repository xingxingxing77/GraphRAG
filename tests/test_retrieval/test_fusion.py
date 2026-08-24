"""融合三件套测试（单元 3.5 S3，07 §5 断言）。

断言：RRF 排序稳定性；归一化区间 [0,1]；Top-20 输出送精排口径；
去重保留最高分且保持排序。
"""

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import RetrievalResult, SourceKind
from app.retrieval.deduplicator import Deduplicator
from app.retrieval.fusion import FusionEngine
from app.retrieval.normalizer import ScoreNormalizer


def _mk(rid: str, content: str, score: float, source: SourceKind, chunk_id: str | None = None) -> RetrievalResult:
    """构造 RetrievalResult 测试数据。"""
    return RetrievalResult(
        result_id=rid,
        chunk_id=chunk_id,
        content=content,
        score=score,
        source=source,
        doc_id=None,
        metadata={},
    )


class TestNormalizer:
    """归一化区间 [0,1] 断言。"""

    def test_min_max_in_range(self) -> None:
        results = [
            _mk("a", "x", 0.9, SourceKind.DENSE),
            _mk("b", "y", 0.5, SourceKind.DENSE),
            _mk("c", "z", 0.1, SourceKind.DENSE),
        ]
        normed = ScoreNormalizer.min_max_normalize(results)
        for r in normed:
            assert 0.0 <= r.score <= 1.0
        assert normed[0].score == 1.0
        assert normed[2].score == 0.0

    def test_single_path_degradation(self) -> None:
        """单路退化：分数全相同 → 统一 1.0。"""
        results = [
            _mk("a", "x", 0.5, SourceKind.DENSE),
            _mk("b", "y", 0.5, SourceKind.DENSE),
        ]
        normed = ScoreNormalizer.min_max_normalize(results)
        assert all(r.score == 1.0 for r in normed)

    def test_rank_normalize_bounds(self) -> None:
        results = [_mk(f"r{i}", f"c{i}", 1.0 - i * 0.1, SourceKind.DENSE) for i in range(4)]
        normed = ScoreNormalizer.rank_normalize(results)
        assert normed[0].score == 1.0
        assert normed[-1].score == 0.0
        for r in normed:
            assert 0.0 <= r.score <= 1.0


class TestRRFFusion:
    """RRF 排序稳定性。"""

    def test_rrf_deterministic_order(self) -> None:
        engine = FusionEngine(strategy="rrf", rrf_k=60)
        dense = [
            _mk("d1", "共现文档", 0.9, SourceKind.DENSE, chunk_id="c1"),
            _mk("d2", "仅dense", 0.7, SourceKind.DENSE, chunk_id="c2"),
        ]
        sparse = [
            _mk("s1", "共现文档", 0.8, SourceKind.SPARSE, chunk_id="c1"),
            _mk("s3", "仅sparse", 0.6, SourceKind.SPARSE, chunk_id="c3"),
        ]
        r1 = engine.fuse({"dense": dense, "sparse": sparse}, top_n=20)
        r2 = engine.fuse({"dense": dense, "sparse": sparse}, top_n=20)
        assert [r.result_id for r in r1] == [r.result_id for r in r2]  # 稳定
        # 共现文档（双路 rank=1）RRF 分最高
        assert r1[0].chunk_id == "c1"

    def test_rrf_top_n_limit(self) -> None:
        engine = FusionEngine(strategy="rrf")
        dense = [_mk(f"d{i}", f"c{i}", 1.0 - i * 0.01, SourceKind.DENSE) for i in range(30)]
        fused = engine.fuse({"dense": dense}, top_n=20)
        assert len(fused) == 20  # Top-20 输出送精排


class TestWeightedFusion:
    """加权融合。"""

    def test_weighted_uses_weights(self) -> None:
        engine = FusionEngine(
            strategy="weighted", weights={"dense": 1.0, "sparse": 0.0}
        )
        dense = [_mk("d1", "仅dense", 0.9, SourceKind.DENSE)]
        sparse = [_mk("s1", "仅sparse", 0.9, SourceKind.SPARSE)]
        fused = engine.fuse({"dense": dense, "sparse": sparse}, top_n=20)
        # dense 权重 1.0 → 排第一；sparse 权重 0 → 分数 0
        assert fused[0].result_id == "d1"

    def test_cross_source_same_chunk_merged(self) -> None:
        """跨路同 chunk_id 合并为一条。"""
        engine = FusionEngine(strategy="weighted", weights={"dense": 0.5, "sparse": 0.5})
        dense = [_mk("d1", "同一块", 0.9, SourceKind.DENSE, chunk_id="shared")]
        sparse = [_mk("s1", "同一块", 0.8, SourceKind.SPARSE, chunk_id="shared")]
        fused = engine.fuse({"dense": dense, "sparse": sparse}, top_n=20)
        assert len(fused) == 1
        assert fused[0].chunk_id == "shared"


class TestDeduplicator:
    """去重（key=result_id）。"""

    def test_dedup_keeps_highest_score(self) -> None:
        results = [
            _mk("r1", "内容A", 0.5, SourceKind.DENSE),
            _mk("r1", "内容A", 0.9, SourceKind.DENSE),
            _mk("r2", "内容B", 0.3, SourceKind.DENSE),
        ]
        deduped = Deduplicator.deduplicate(results, strategy="result_id")
        assert len(deduped) == 2
        assert deduped[0].score == 0.9  # 保留最高分

    def test_dedup_preserves_order(self) -> None:
        results = [
            _mk("r1", "A", 0.9, SourceKind.DENSE),
            _mk("r2", "B", 0.8, SourceKind.SPARSE),
            _mk("r1", "A", 0.7, SourceKind.DENSE),
        ]
        deduped = Deduplicator.deduplicate(results)
        assert [r.result_id for r in deduped] == ["r1", "r2"]

    def test_content_hash_strategy(self) -> None:
        results = [
            _mk("r1", "相同内容", 0.5, SourceKind.DENSE),
            _mk("r2", "相同内容", 0.9, SourceKind.SPARSE),
        ]
        deduped = Deduplicator.deduplicate(results, strategy="content_hash")
        assert len(deduped) == 1
        assert deduped[0].score == 0.9
