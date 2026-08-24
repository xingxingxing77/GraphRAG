"""dense/sparse 检索器测试（单元 3.3 S3，07 §5 断言）。

断言：result_id 唯一性与 source 口径；超时/失败降级空列表 + 计数；
asyncio.gather 双路并行骨架就绪。
"""

# --- 标准库 ---
import asyncio

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import EmbeddingResult, SourceKind
from app.retrieval.dense_retriever import DenseRetriever, stable_hash
from app.retrieval.sparse_retriever import SparseRetriever


class FakeEmbedder:
    """Embedding 测试替身。"""

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """返回固定 dense/sparse 向量。"""
        n = len(texts)
        return EmbeddingResult(
            dense=[[0.1, 0.2, 0.3] for _ in range(n)],
            sparse=[{1: 1.0, 2: 0.5} for _ in range(n)],
        )


class FakeQdrant:
    """Qdrant 测试替身：可控延迟/异常/命中。"""

    def __init__(
        self, delay: float = 0.0, raise_exc: bool = False, hits: int = 2
    ) -> None:
        """初始化替身。

        Args:
            delay: search 延迟（秒）。
            raise_exc: 是否抛异常。
            hits: 命中数。
        """
        self.delay = delay
        self.raise_exc = raise_exc
        self.hits = hits

    async def search(self, collection: str, query_vector, top_k: int = 10):
        """模拟 dense search。"""
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raise_exc:
            raise RuntimeError("qdrant down")
        return [
            {
                "id": f"pt-{collection}-{i}",
                "chunk_id": f"doc-{i}",
                "score": 0.9 - i * 0.1,
                "payload": {"content": f"内容{i}", "doc_id": "doc", "chunk_id": f"doc-{i}"},
            }
            for i in range(self.hits)
        ]

    async def search_sparse(self, collection: str, sparse_vector, top_k: int = 10):
        """模拟 sparse search（同 search）。"""
        return await self.search(collection, sparse_vector, top_k)

    async def list_collections(self) -> list[str]:
        """模拟集合列表。"""
        return ["rag_recipes", "rag_tips"]


class TestResultIdAndScore:
    """result_id 唯一性与 score 口径（07 §5）。"""

    @pytest.mark.asyncio
    async def test_result_id_unique_and_prefixed(self) -> None:
        retriever = DenseRetriever(FakeQdrant(hits=3), FakeEmbedder(), ["rag_recipes"])
        results = await retriever.retrieve("清蒸鲈鱼", top_k=3)
        assert len(results) == 3
        ids = [r.result_id for r in results]
        assert len(set(ids)) == 3  # 唯一
        for r in results:
            assert r.result_id.startswith("dense:")
            assert r.source == SourceKind.DENSE

    @pytest.mark.asyncio
    async def test_sparse_result_id_prefixed(self) -> None:
        retriever = SparseRetriever(FakeQdrant(hits=2), FakeEmbedder(), ["rag_recipes"])
        results = await retriever.retrieve("清蒸鲈鱼", top_k=2)
        for r in results:
            assert r.result_id.startswith("sparse:")
            assert r.source == SourceKind.SPARSE

    @pytest.mark.asyncio
    async def test_score_sorted_desc_raw(self) -> None:
        retriever = DenseRetriever(FakeQdrant(hits=3), FakeEmbedder(), ["rag_recipes"])
        results = await retriever.retrieve("q", top_k=3)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_stable_hash_deterministic(self) -> None:
        assert stable_hash("a", "b") == stable_hash("a", "b")
        assert stable_hash("a", "b") != stable_hash("b", "a")


class TestDegradation:
    """超时/失败降级空列表（D5）。"""

    @pytest.mark.asyncio
    async def test_timeout_returns_empty_and_counts(self) -> None:
        retriever = DenseRetriever(
            FakeQdrant(delay=1.0), FakeEmbedder(), ["rag_recipes"], timeout_s=0.05
        )
        results = await retriever.retrieve("q", top_k=2)
        assert results == []
        assert retriever.error_count == 1

    @pytest.mark.asyncio
    async def test_exception_returns_empty_and_counts(self) -> None:
        retriever = SparseRetriever(
            FakeQdrant(raise_exc=True), FakeEmbedder(), ["rag_recipes"]
        )
        results = await retriever.retrieve("q", top_k=2)
        assert results == []
        assert retriever.error_count == 1

    @pytest.mark.asyncio
    async def test_empty_sparse_vector_returns_empty(self) -> None:
        class EmptySparseEmbedder:
            async def embed(self, texts):
                return EmbeddingResult(dense=[[0.1]], sparse=[{}])

        retriever = SparseRetriever(FakeQdrant(), EmptySparseEmbedder(), ["rag_recipes"])
        assert await retriever.retrieve("q", top_k=2) == []


class TestParallelSkeleton:
    """asyncio.gather 并行骨架（准出：六路并行就绪）。"""

    @pytest.mark.asyncio
    async def test_gather_dense_sparse_parallel(self) -> None:
        dense = DenseRetriever(FakeQdrant(hits=2), FakeEmbedder(), ["rag_recipes"])
        sparse = SparseRetriever(FakeQdrant(hits=2), FakeEmbedder(), ["rag_recipes"])
        results = await asyncio.gather(
            dense.retrieve("q", 2),
            sparse.retrieve("q", 2),
            return_exceptions=True,
        )
        assert all(isinstance(r, list) for r in results)
        assert len(results[0]) == 2
        assert len(results[1]) == 2

    @pytest.mark.asyncio
    async def test_one_failure_not_block_other(self) -> None:
        """单路失败不阻塞其余路（gather return_exceptions）。"""
        ok = DenseRetriever(FakeQdrant(hits=2), FakeEmbedder(), ["rag_recipes"])
        bad = SparseRetriever(FakeQdrant(raise_exc=True), FakeEmbedder(), ["rag_recipes"])
        results = await asyncio.gather(
            ok.retrieve("q", 2),
            bad.retrieve("q", 2),
            return_exceptions=True,
        )
        assert isinstance(results[0], list) and len(results[0]) == 2
        assert isinstance(results[1], list) and results[1] == []  # 降级空列表非异常
