"""记忆注入调度器测试（单元 8.1/8.2 S3：双闸去重 + 注入格式）。"""

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.memory.working_memory import WorkingMemory
from app.memory.episodic import EpisodicMemory
from app.memory.scheduler import MemoryScheduler
from tests.test_memory.conftest import FakeEmbedder, FakeQdrant, FakeRedis

WM_QA = ("鲈鱼怎么蒸", "冷水上锅蒸8分钟")


def _wm_text() -> str:
    return f"Q: {WM_QA[0]}\nA: {WM_QA[1]}"


async def _seed_working_memory(scheduler: MemoryScheduler) -> None:
    await scheduler.working_memory.add_exchange("s-cur", WM_QA[0], WM_QA[1])


def _make_scheduler(
    overrides: dict[str, list[float]] | None = None,
) -> tuple[MemoryScheduler, EpisodicMemory]:
    embedder = FakeEmbedder(dim=2, overrides=overrides)
    episodic = EpisodicMemory(FakeQdrant(), embedder)
    scheduler = MemoryScheduler(
        WorkingMemory(FakeRedis()),
        episodic,
        embedder,
        working_turns=6,
        episodic_top_m=3,
    )
    return scheduler, episodic


class TestDualGateDedup:

    async def test_gate1_exact_hash_removed(self) -> None:
        scheduler, episodic = _make_scheduler()
        await _seed_working_memory(scheduler)
        # 情景片段与工作记忆完全同文（hash 相同）→ 闸 1 剔除
        await episodic.add("s-old", "u1", 1, WM_QA[0], WM_QA[1])
        ctx = await scheduler.build_context("u1", "s-cur", "还要注意什么")
        assert ctx.episodic_hits == 0
        assert ctx.dedup_removed == 1

    async def test_gate2_high_similarity_removed_low_kept(self) -> None:
        overrides = {
            _wm_text(): [1.0, 0.0],
            # 候选 A：cos≈0.95 > 0.92 → 剔除；候选 B：cos=0.6 → 保留
            "近似问题\n近似答案": [0.95, 0.3122],
            "无关话题\n无关答案": [0.6, 0.8],
        }
        scheduler, episodic = _make_scheduler(overrides)
        await _seed_working_memory(scheduler)
        await episodic.add("s-old", "u1", 1, "近似问题", "近似答案")
        await episodic.add("s-older", "u1", 1, "无关话题", "无关答案")
        ctx = await scheduler.build_context("u1", "s-cur", "烹饪技巧")
        assert ctx.dedup_removed == 1
        assert ctx.episodic_hits == 1
        assert ctx.context_text.count("无关话题") == 1

    async def test_no_duplicates_when_history_empty(self) -> None:
        scheduler, episodic = _make_scheduler()
        await episodic.add("s-old", "u1", 1, "历史问题", "历史答案")
        ctx = await scheduler.build_context("u1", "s-cur", "新查询")
        assert ctx.injected_working_turns == 0
        assert ctx.episodic_hits == 1


class TestContextFormat:

    async def test_two_section_format_and_counts(self) -> None:
        scheduler, episodic = _make_scheduler()
        await _seed_working_memory(scheduler)
        await episodic.add("s-old", "u1", 1, "旧问题", "旧答案")
        ctx = await scheduler.build_context("u1", "s-cur", "火候")
        assert ctx.context_text.startswith("[历史1轮]")
        assert "[相关记忆" in ctx.context_text
        assert ctx.injected_working_turns == 1

    async def test_empty_state_yields_empty_context(self) -> None:
        scheduler, _ = _make_scheduler()
        ctx = await scheduler.build_context("u1", "s-new", "第一句问话")
        assert ctx.context_text == ""
        assert ctx.injected_working_turns == 0
        assert ctx.episodic_hits == 0

    async def test_working_turns_window_respected(self) -> None:
        embedder = FakeEmbedder()
        scheduler = MemoryScheduler(
            WorkingMemory(FakeRedis()),
            EpisodicMemory(FakeQdrant(), embedder),
            embedder,
            working_turns=2,
        )
        conv = scheduler.working_memory
        for i in range(4):
            await conv.add_exchange("s-cur", f"q{i}", f"a{i}")
        ctx = await scheduler.build_context("u1", "s-cur", "当前问题")
        assert ctx.injected_working_turns == 2
