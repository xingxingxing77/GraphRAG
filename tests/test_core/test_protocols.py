"""三 Protocol 结构子类型冒烟测试（单元 0.3 S3，07 §5）。

runtime_checkable Protocol 的 isinstance 检查仅验证属性/方法存在性，
签名一致性由各实现类的集成测试保障。
"""

# --- 本地模块 ---
from app.core.models import EmbeddingResult, RetrievalResult, SourceKind
from app.embedding.base import EmbeddingService
from app.reranking.base import RerankerService
from app.retrieval.base import BaseRetriever


class FakeRetriever:
    """符合 BaseRetriever 协议的最小实现。"""

    name = SourceKind.DENSE
    error_count = 0

    async def retrieve(
        self,
        query: str,
        top_k: int,
        filters: dict | None = None,
    ) -> list[RetrievalResult]:
        return []


class FakeReranker:
    """符合 RerankerService 协议的最小实现。"""

    async def rerank(
        self,
        query: str,
        docs: list[RetrievalResult],
        top_k: int,
    ) -> list[tuple[RetrievalResult, float]]:
        return [(doc, doc.score) for doc in docs[:top_k]]


class FakeEmbedder:
    """符合 EmbeddingService 协议的最小实现。"""

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult()


class TestProtocolConformance:
    """Protocol 结构子类型检查（runtime_checkable 冒烟）。"""

    def test_retriever_conforms(self) -> None:
        assert isinstance(FakeRetriever(), BaseRetriever)

    def test_reranker_conforms(self) -> None:
        assert isinstance(FakeReranker(), RerankerService)

    def test_embedding_conforms(self) -> None:
        assert isinstance(FakeEmbedder(), EmbeddingService)

    def test_non_conforming_rejected(self) -> None:
        class NotARetriever:
            pass

        assert not isinstance(NotARetriever(), BaseRetriever)
