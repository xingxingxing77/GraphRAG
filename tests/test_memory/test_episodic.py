"""情景记忆测试（单元 8.2 S3，07 §5 A-05：session 隔离与删除联动）。"""

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.memory.episodic import RAG_EPISODIC_COLLECTION, EpisodicMemory
from tests.test_memory.conftest import FakeEmbedder, FakeQdrant


def _make_memory() -> tuple[EpisodicMemory, FakeQdrant]:
    qdrant = FakeQdrant()
    return EpisodicMemory(qdrant, FakeEmbedder(dim=8)), qdrant


class TestEpisodicMemory:

    async def test_add_is_idempotent_on_same_turn(self) -> None:
        memory, qdrant = _make_memory()
        for _ in range(2):  # 同轮重复写（管道重放）
            await memory.add("s1", "u1", 1, "q1", "a1")
        assert qdrant.count(RAG_EPISODIC_COLLECTION) == 1

    async def test_search_filters_by_user_and_excludes_current_session(self) -> None:
        memory, _ = _make_memory()
        await memory.add("s-old", "u1", 1, "清蒸鲈鱼火候", "蒸8分钟")
        await memory.add("s-other", "u2", 1, "清蒸鲈鱼火候", "蒸8分钟")
        await memory.add("s-cur", "u1", 1, "清蒸鲈鱼火候", "蒸8分钟")

        hits = await memory.search(
            "u1", "鲈鱼蒸几分钟", top_m=5, exclude_session="s-cur"
        )
        assert {h.session_id for h in hits} == {"s-old"}  # 用户隔离 + 排除当前会话

    async def test_delete_by_session_cascades(self) -> None:
        memory, qdrant = _make_memory()
        await memory.add("s1", "u1", 1, "q1", "a1")
        await memory.add("s1", "u1", 2, "q2", "a2")
        await memory.add("s2", "u1", 1, "q3", "a3")
        await memory.delete_by_session("s1")
        # A-05：仅删除目标会话
        assert qdrant.count(RAG_EPISODIC_COLLECTION) == 1

    async def test_purge_expired_removes_only_old_points(self) -> None:
        memory, qdrant = _make_memory()
        now = 1_800_000_000
        await memory.add("s1", "u1", 1, "q1", "a1", timestamp=now - 200 * 86400)
        await memory.add("s1", "u1", 2, "q2", "a2", timestamp=now - 10 * 86400)
        deleted = await memory.purge_expired(now=now)  # D8：180 天保留期
        assert deleted == 1
        assert qdrant.count(RAG_EPISODIC_COLLECTION) == 1

    async def test_search_swallows_storage_failure(self) -> None:
        class BrokenQdrant(FakeQdrant):
            async def search(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
                raise RuntimeError("down")

        memory = EpisodicMemory(BrokenQdrant(), FakeEmbedder())
        assert await memory.search("u1", "任意") == []
