"""工作记忆测试（单元 8.1 S3，07 §6 E-05 / A-05 断言）。"""

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.memory.working_memory import WM_TTL_SECONDS, WorkingMemory
from tests.test_memory.conftest import FakeRedis


class TestWorkingMemory:

    @pytest.fixture
    def memory(self) -> WorkingMemory:
        return WorkingMemory(FakeRedis(), max_turns=3)

    async def test_add_exchange_sets_wm_key_ttl_and_entry(self, memory: WorkingMemory) -> None:
        redis = memory.redis
        assert isinstance(redis, FakeRedis)
        await memory.add_exchange("s1", "怎么做鱼", "清蒸即可")
        assert "wm:s1" in redis.lists
        # TTL 7d（04 §4）
        assert redis.ttls["wm:s1"] == WM_TTL_SECONDS
        entry = __import__("json").loads(redis.lists["wm:s1"][0])
        assert entry["q"] == "怎么做鱼"
        assert entry["a"] == "清蒸即可"
        assert isinstance(entry["ts"], int)

    async def test_sliding_window_trims_to_max_turns(self, memory: WorkingMemory) -> None:
        for i in range(5):
            await memory.add_exchange("s1", f"q{i}", f"a{i}")
        history = await memory.get_history("s1")
        # LTRIM 保留最近 3 轮，且旧→新排序
        assert [h["q"] for h in history] == ["q2", "q3", "q4"]

    async def test_get_history_last_n_subset(self, memory: WorkingMemory) -> None:
        for i in range(3):
            await memory.add_exchange("s1", f"q{i}", f"a{i}")
        history = await memory.get_history("s1", last_n=2)
        assert [h["q"] for h in history] == ["q1", "q2"]

    async def test_clear_removes_key(self, memory: WorkingMemory) -> None:
        await memory.add_exchange("s1", "q", "a")
        await memory.clear("s1")
        assert await memory.get_history("s1") == []
        assert "wm:s1" not in memory.redis.lists  # type: ignore[attr-defined]
