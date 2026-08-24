"""语义缓存测试（单元 8.3 S3，07 §5 A-10/A-11 + 11 路线图 Phase 4）。"""

# --- 标准库 ---
import asyncio
import time

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.memory.semantic_cache import (
    L2_KEY_PREFIX,
    L1Entry,
    RAG_CACHE_COLLECTION,
    SemanticCache,
)
from tests.test_memory.conftest import FakeEmbedder, FakeQdrant, FakeRedis

HIT_QUERY = "清蒸鲈鱼怎么做"
PARAPHRASE = "鲈鱼如何清蒸"  # 预置向量 cos≈0.70 → miss


def _make_cache(
    overrides: dict[str, list[float]] | None = None,
) -> tuple[SemanticCache, FakeQdrant, FakeRedis]:
    qdrant = FakeQdrant()
    redis = FakeRedis()
    embedder = FakeEmbedder(dim=2, overrides=overrides)
    return SemanticCache(qdrant, embedder, redis), qdrant, redis


def _entry(question: str = HIT_QUERY) -> L1Entry:
    return L1Entry(
        question=question,
        answer="冷水上锅蒸 8 分钟",
        latency_tier="fast",
        model="deepseek-chat",
        matched_doc_ids=["doc-1"],
    )


class TestL1Ann:

    async def test_hit_at_threshold_and_payload_roundtrip(self) -> None:
        cache, _, _ = _make_cache(overrides={HIT_QUERY: [1.0, 0.0]})
        await cache.set_l1(_entry())
        result = await cache.get_l1(HIT_QUERY)
        assert result.hit is True
        assert not result.degraded
        assert result.cache_score >= 0.95
        assert result.answer == "冷水上锅蒸 8 分钟"
        assert result.matched_query == HIT_QUERY
        assert result.model == "deepseek-chat"

    async def test_paraphrase_miss_below_threshold_returns_score(self) -> None:
        cache, _, _ = _make_cache(
            overrides={HIT_QUERY: [1.0, 0.0], PARAPHRASE: [0.7, 0.714]}
        )
        await cache.set_l1(_entry())
        result = await cache.get_l1(PARAPHRASE)
        # 同义改写相似度不足 → miss 但带分数（ANN 语义能力生效的证据）
        assert result.hit is False
        assert result.cache_score is not None and result.cache_score < 0.95
        assert not result.degraded

    async def test_qdrant_failure_degrades_to_miss_not_raise(self) -> None:
        class BrokenQdrant(FakeQdrant):
            async def search(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
                raise RuntimeError("qdrant down")

        cache = SemanticCache(BrokenQdrant(), FakeEmbedder(), FakeRedis())
        result = await cache.get_l1(HIT_QUERY)
        # A-11：存储异常 → {hit:false} + degraded，不抛错不阻塞
        assert result.hit is False and result.degraded is True

    async def test_read_filters_expired_entries(self) -> None:
        overrides = {HIT_QUERY: [1.0, 0.0]}
        cache, qdrant, _ = _make_cache(overrides=overrides)
        await cache.set_l1(_entry())
        # 人为把 created_at 改为过期时刻
        bucket = qdrant.points["rag_cache"]
        for rec in bucket.values():
            rec["payload"]["created_at"] = int(time.time()) - cache.l1_ttl_seconds - 10
        assert (await cache.get_l1(HIT_QUERY)).hit is False

    async def test_invalidate_doc_removes_affected_entry(self) -> None:
        cache, qdrant, _ = _make_cache(overrides={HIT_QUERY: [1.0, 0.0]})
        await cache.set_l1(_entry())
        await cache.invalidate_doc("doc-1")
        assert qdrant.count("rag_cache") == 0

    async def test_purge_expired_only_deletes_stale(self) -> None:
        cache, qdrant, _ = _make_cache(overrides={HIT_QUERY: [1.0, 0.0]})
        await cache.set_l1(_entry(HIT_QUERY))
        # 第二条新鲜点（问题不同向量无所谓，仅考察 created_at）
        await cache.set_l1(L1Entry(question="红烧肉怎么做", answer="炖 40 分钟"))
        for rec in qdrant.points[RAG_CACHE_COLLECTION].values():
            if rec["payload"]["question"] == HIT_QUERY:
                rec["payload"]["created_at"] = 1  # 远古
        deleted = await cache.purge_expired()
        assert deleted == 1
        assert qdrant.count(RAG_CACHE_COLLECTION) == 1


class TestSingleFlight:

    async def test_concurrent_misses_share_one_loader(self) -> None:
        overrides = {HIT_QUERY: [1.0, 0.0], "其他问题": [0.0, 1.0]}
        cache, _, _ = _make_cache(overrides=overrides)
        calls = 0

        async def loader() -> L1Entry:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return _entry()

        results = await asyncio.gather(
            *(cache.get_or_load("其他问题", loader) for _ in range(5))
        )
        assert calls == 1
        assert all(r.hit for r in results)

    async def test_inflight_cleared_after_completion(self) -> None:
        cache, _, _ = _make_cache(overrides={"q9": [0.0, 1.0]})

        async def loader() -> L1Entry:
            return _entry("q9")

        await cache.get_or_load("q9", loader)
        await asyncio.sleep(0)
        assert cache._inflight == {}


class TestL2:

    async def test_l2_key_format_ttl_and_roundtrip(self) -> None:
        cache, _, redis = _make_cache()
        payload = [{"result_id": "dense:x", "score": 0.9}]
        await cache.set_l2("鱼的做法", payload, params={"tier": "fast"})
        key = L2_KEY_PREFIX + cache.norm_hash("鱼的做法", {"tier": "fast"})
        assert len(cache.norm_hash("鱼的做法")) == 24
        assert key in redis.strings
        assert redis.ttls[key] == cache.l2_ttl_seconds
        assert (await cache.get_l2("鱼的做法", {"tier": "fast"})) == payload

    async def test_l2_redis_down_returns_none(self) -> None:
        class BrokenRedis(FakeRedis):
            async def get(self, key: str) -> None:
                raise RuntimeError("redis down")

        cache = SemanticCache(FakeQdrant(), FakeEmbedder(), BrokenRedis())  # type: ignore[arg-type]
        assert await cache.get_l2("任意") is None

    async def test_normalize_collapses_case_and_space(self) -> None:
        assert (
            SemanticCache.normalize("  How   to Steam FISH ")
            == "how to steam fish"
        )
