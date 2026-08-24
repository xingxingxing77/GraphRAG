"""Qdrant 业务集合写入测试（单元 3.1 S3，07 §5 断言）。

断言：payload 键规范校验（04 §3.1）；batch 幂等重放（双写 count 不变）；
集合命名 rag_{doc_type}；doc_id 过滤 scroll/delete。
"""

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import (
    Chunk,
    EmbeddingResult,
    EnrichedChunk,
    MetadataKeys,
    PositionMeta,
)
from app.db.qdrant_client import QdrantDBClient, point_id_from_chunk_id
from app.pipeline.indexing.vector_indexer import (
    VectorIndexer,
    build_payload,
    collection_for,
)

_TEST_PREFIX = "__test_3_1__"
_TEST_DOC_TYPE = "testunit"


class FakeEmbedder:
    """Embedding 测试替身：固定维度向量。"""

    def __init__(self, dim: int = 1024) -> None:
        """初始化替身。

        Args:
            dim: 密集向量维度。
        """
        self.dim = dim

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """返回固定 dense 向量与简单 sparse。"""
        dense = [[float(i + 1)] * self.dim for i in range(len(texts))]
        sparse = [{i + 1: 1.0, i + 2: 0.5} for i in range(len(texts))]
        return EmbeddingResult(dense=dense, sparse=sparse)


def _enriched_chunks() -> list[EnrichedChunk]:
    """构造两个测试 EnrichedChunk。"""
    chunks = []
    for seq in range(2):
        chunk = Chunk(
            chunk_id=f"{_TEST_PREFIX}doc-{seq}",
            doc_id=f"{_TEST_PREFIX}doc",
            seq=seq,
            content=f"测试内容 {seq}",
            title_path=["测试"],
            position=PositionMeta(start_char=0, end_char=6),
            metadata={MetadataKeys.QUALITY_SCORE: 0.9},
        )
        chunks.append(
            EnrichedChunk(chunk=chunk, keywords=["测试"], summary=None)
        )
    return chunks


class TestPayloadSpec:
    """payload 键规范（04 §3.1）。"""

    def test_required_keys_present(self) -> None:
        chunks = _enriched_chunks()
        payload = build_payload(chunks[0], source="menu/test.md", doc_type="recipes")
        # 必填键
        assert payload[MetadataKeys.DOC_ID] == f"{_TEST_PREFIX}doc"
        assert payload[MetadataKeys.CHUNK_ID] == f"{_TEST_PREFIX}doc-0"
        assert payload[MetadataKeys.SOURCE] == "menu/test.md"
        assert payload[MetadataKeys.DOC_TYPE] == "recipes"
        # 附加键
        assert payload["content"] == "测试内容 0"
        assert payload["keywords"] == ["测试"]
        assert payload["access_count"] == 0
        assert payload[MetadataKeys.QUALITY_SCORE] == 0.9
        assert payload[MetadataKeys.TITLE_PATH] == ["测试"]

    def test_collection_naming(self) -> None:
        assert collection_for("recipes") == "rag_recipes"
        assert collection_for("tips") == "rag_tips"

    def test_point_id_deterministic(self) -> None:
        assert point_id_from_chunk_id("a-0") == point_id_from_chunk_id("a-0")
        assert point_id_from_chunk_id("a-0") != point_id_from_chunk_id("a-1")


class TestVectorIndexerQdrant:
    """Qdrant 集成（不可达时跳过）。"""

    @pytest.mark.asyncio
    async def test_idempotent_upsert_and_scroll(self) -> None:
        client = QdrantDBClient(host="localhost", port=6333)
        if not await client.check_health():
            pytest.skip("Qdrant 不可达，集成用例跳过")
        collection = collection_for(_TEST_DOC_TYPE)
        indexer = VectorIndexer(client, FakeEmbedder())
        chunks = _enriched_chunks()
        try:
            # 首次写入
            n1 = await indexer.index(chunks, source="menu/test.md", doc_type=_TEST_DOC_TYPE)
            assert n1 == 2
            count1 = await client.count(collection)
            assert count1 >= 2

            # 幂等重放：双写 count 不变（07 §5）
            await indexer.index(chunks, source="menu/test.md", doc_type=_TEST_DOC_TYPE)
            count2 = await client.count(collection)
            assert count2 == count1

            # doc_id 过滤 scroll
            points = await client.scroll_by_doc(collection, f"{_TEST_PREFIX}doc")
            assert len(points) == 2
            payload = points[0]["payload"]
            assert payload[MetadataKeys.DOC_ID] == f"{_TEST_PREFIX}doc"
            assert payload[MetadataKeys.DOC_TYPE] == _TEST_DOC_TYPE

            # dense 检索可命中
            hits = await client.search(collection, [1.0] * 1024, top_k=2)
            assert len(hits) == 2
            assert hits[0]["score"] > 0
        finally:
            await client.delete_by_doc(collection, f"{_TEST_PREFIX}doc")
            await client.close()
