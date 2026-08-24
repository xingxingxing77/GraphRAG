"""用户画像测试（单元 8.2 S3，11 路线图 Phase 4 断言）。"""

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.memory.user_profile import SUMMARIES_CAP, UserProfile
from tests.test_memory.conftest import FakeRedis


class TestUserProfile:

    @pytest.fixture
    def profile(self) -> UserProfile:
        return UserProfile(FakeRedis())

    async def test_get_profile_default_empty(self, profile: UserProfile) -> None:
        result = await profile.get_profile("u1")
        assert result == {"preferences": {}, "summary": "", "updated_at": None}

    async def test_update_preferences_writes_hash_and_updated_at(
        self, profile: UserProfile
    ) -> None:
        await profile.update_preferences("u1", {"taste": "清淡"})
        result = await profile.get_profile("u1")
        assert result["preferences"] == {"taste": "清淡"}
        assert result["updated_at"] is not None

    async def test_summaries_capped_by_ltrim(self, profile: UserProfile) -> None:
        for i in range(SUMMARIES_CAP + 5):
            await profile.add_summary("u1", f"摘要{i}")
        summaries = await profile.get_summaries("u1")
        # LTRIM 20 封顶，保留最新 20 条，旧→新排序
        assert len(summaries) == SUMMARIES_CAP
        assert summaries[0] == f"摘要{5}"
        assert summaries[-1] == f"摘要{SUMMARIES_CAP + 4}"

    async def test_distill_with_summarizer_merges_into_summary(
        self, profile: UserProfile
    ) -> None:
        calls: list[list[str]] = []

        async def fake_summarizer(summaries: list[str]) -> str:
            calls.append(summaries)
            return "合并画像:" + "|".join(summaries)

        profile.summarizer = fake_summarizer
        await profile.add_summary("u1", "喜欢家常菜")
        await profile.add_summary("u1", "偏好视频教程")
        merged = await profile.distill("u1")
        assert merged.startswith("合并画像:")
        assert len(calls[0]) == 2
        result = await profile.get_profile("u1")
        assert result["summary"] == merged

    async def test_distill_fallback_truncation_without_summarizer(
        self, profile: UserProfile
    ) -> None:
        await profile.add_summary("u1", "A" * 1500)
        await profile.add_summary("u1", "B" * 1500)
        merged = await profile.distill("u1")
        assert len(merged) == 2000

    async def test_distill_noop_on_empty_source(self, profile: UserProfile) -> None:
        assert await profile.distill("ghost") == ""
