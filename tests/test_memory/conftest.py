"""记忆层测试替身（07 §3 stub 思路，离线可跑）。

FakeRedis/FakeQdrant 为内存语义等价实现，覆盖记忆层实际使用的
方法面；FakeEmbedder 提供确定性向量：同文本恒同向量，不同文本
近似正交，并支持按文本预置向量以构造阈值边界场景。
"""

# --- 标准库 ---
import hashlib
from collections import defaultdict
from typing import Any

# --- 本地模块 ---
from app.core.models import EmbeddingResult


class FakeRedis:
    """redis.asyncio 最小内存替身。"""

    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = defaultdict(dict)
        self.lists: dict[str, list[str]] = defaultdict(list)
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.strings.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        self.strings[key] = value
        if ttl is not None:
            self.ttls[key] = ttl

    async def delete(self, key: str) -> None:
        self.strings.pop(key, None)
        self.hashes.pop(key, None)
        self.lists.pop(key, None)
        self.ttls.pop(key, None)

    async def hgetall(self, name: str) -> dict[str, str]:
        return dict(self.hashes.get(name, {}))

    async def hset(self, name: str, key: str, value: str) -> None:
        self.hashes[name][key] = value

    async def lpush(self, name: str, *values: str) -> None:
        self.lists[name][:0] = values

    async def ltrim(self, name: str, start: int, end: int) -> None:
        stop = None if end < 0 else end + 1
        self.lists[name] = self.lists[name][start:stop]

    async def lrange(self, name: str, start: int, end: int) -> list[str]:
        stop = None if end < 0 else end + 1
        return list(self.lists.get(name, [])[start:stop])

    async def expire(self, key: str, ttl: int) -> None:
        self.ttls[key] = ttl


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class FakeQdrant:
    """QdrantDBClient 记忆层方法面的内存替身（真实余弦计算）。"""

    def __init__(self) -> None:
        self.collections: set[str] = set()
        self.points: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    async def ensure_collection(
        self, collection_name: str, dense_vector_size: int = 1024, distance: Any = None
    ) -> None:
        self.collections.add(collection_name)

    async def upsert_points(
        self, collection_name: str, points: list[Any], batch_size: int = 100
    ) -> None:
        self.collections.add(collection_name)
        bucket = self.points[collection_name]
        for p in points:
            vec = p.vector["dense"] if isinstance(p.vector, dict) else p.vector
            bucket[str(p.id)] = {"vector": list(vec), "payload": dict(p.payload)}

    def _passes(self, flt: Any, payload: dict[str, Any]) -> bool:
        if flt is None:
            return True
        for cond in getattr(flt, "must", None) or []:
            if not self._match(cond, payload):
                return False
        for cond in getattr(flt, "must_not", None) or []:
            if self._match(cond, payload):
                return False
        return True

    @staticmethod
    def _match(cond: Any, payload: dict[str, Any]) -> bool:
        value = payload.get(cond.key)
        rng = getattr(cond, "range", None)
        if rng is not None:
            if value is None:
                return False
            if getattr(rng, "gte", None) is not None and value < rng.gte:
                return False
            if getattr(rng, "lt", None) is not None and value >= rng.lt:
                return False
            return True
        match_value = cond.match.value if cond.match is not None else None
        if isinstance(value, list):
            return match_value in value
        return value == match_value

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int = 10,
        filter_condition: Any = None,
    ) -> list[dict[str, Any]]:
        bucket = self.points.get(collection_name, {})
        scored = [
            {
                "id": pid,
                "chunk_id": "",
                "score": _cosine(query_vector, rec["vector"]),
                "payload": rec["payload"],
            }
            for pid, rec in bucket.items()
            if self._passes(filter_condition, rec["payload"])
        ]
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]

    async def delete_by_payload_match(
        self, collection_name: str, key: str, value: Any
    ) -> None:
        bucket = self.points.get(collection_name, {})
        for pid in [
            pid for pid, rec in bucket.items() if self._value_hit(rec["payload"].get(key), value)
        ]:
            del bucket[pid]

    @staticmethod
    def _value_hit(field_value: Any, target: Any) -> bool:
        if isinstance(field_value, list):
            return target in field_value
        return field_value == target

    async def delete_created_before(
        self, collection_name: str, field: str, before_unix: int, batch: int = 500
    ) -> int:
        bucket = self.points.get(collection_name, {})
        stale = [
            pid
            for pid, rec in bucket.items()
            if isinstance(rec["payload"].get(field), (int, float))
            and rec["payload"][field] < before_unix
        ]
        for pid in stale:
            del bucket[pid]
        return len(stale)

    def count(self, collection_name: str) -> int:
        return len(self.points.get(collection_name, {}))


class FakeEmbedder:
    """确定性向量替身：同文本恒同；可用 overrides 构造边界相似度。"""

    def __init__(
        self, dim: int = 16, overrides: dict[str, list[float]] | None = None
    ) -> None:
        self.dim = dim
        self.overrides = overrides or {}

    def _vector(self, text: str) -> list[float]:
        if text in self.overrides:
            return list(self.overrides[text])
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [1.0 if b % 2 == 0 else -1.0 for b in digest[: self.dim]]

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            dense=[self._vector(t) for t in texts],
            sparse=[{} for _ in texts],
        )
