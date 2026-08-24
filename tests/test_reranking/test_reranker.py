"""Reranker 测试（单元 4.1 S3，07 §5 断言）。

断言：并发压测不阻塞事件循环；sleep(3s) 注入走 no-rerank 降级（E-08）；
精排按分降序且截断 top_k；FlagEmbedding 未安装时优雅降级。
"""

# --- 标准库 ---
import asyncio
import time

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import RetrievalResult, SourceKind
from app.reranking.reranker import BGEReranker


def _docs(n: int = 4) -> list[RetrievalResult]:
    """构造粗排候选。"""
    return [
        RetrievalResult(
            result_id=f"d{i}",
            chunk_id=None,
            content=f"文档内容 {i}",
            score=0.9 - i * 0.1,
            source=SourceKind.DENSE,
            doc_id=None,
            metadata={},
        )
        for i in range(n)
    ]


class TestRerankOrdering:
    """精排排序与截断。"""

    @pytest.mark.asyncio
    async def test_rerank_sorts_by_model_score(self) -> None:
        def score_fn(pairs: list[list[str]]) -> list[float]:
            # 反转分数：原文档序 0..3 → 分数 0.1,0.5,0.9,0.3
            return [0.1, 0.5, 0.9, 0.3][: len(pairs)]

        reranker = BGEReranker(score_fn=score_fn)
        ranked = await reranker.rerank("q", _docs(4), top_k=4)
        assert [d.result_id for d, _ in ranked] == ["d2", "d1", "d3", "d0"]
        assert not reranker.last_degraded

    @pytest.mark.asyncio
    async def test_top_k_truncation(self) -> None:
        reranker = BGEReranker(score_fn=lambda pairs: [0.5] * len(pairs))
        ranked = await reranker.rerank("q", _docs(4), top_k=2)
        assert len(ranked) == 2

    @pytest.mark.asyncio
    async def test_empty_docs(self) -> None:
        reranker = BGEReranker(score_fn=lambda pairs: [])
        assert await reranker.rerank("q", [], top_k=5) == []


class TestDegradation:
    """降级路径（E-08）。"""

    @pytest.mark.asyncio
    async def test_slow_scoring_degrades_to_coarse_order(self) -> None:
        """sleep(3s) 注入 → 超时走 no-rerank 降级。"""

        def slow_fn(pairs: list[list[str]]) -> list[float]:
            time.sleep(1.0)  # E-08 慢推理注入（远超 0.05s 超时阈）
            return [1.0] * len(pairs)

        reranker = BGEReranker(score_fn=slow_fn, timeout_s=0.05)
        docs = _docs(4)
        ranked = await reranker.rerank("q", docs, top_k=4)
        assert reranker.last_degraded
        assert reranker.degraded_count == 1
        # 降级返回原序粗排分
        assert [d.result_id for d, _ in ranked] == ["d0", "d1", "d2", "d3"]
        assert ranked[0][1] == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_missing_flagembedding_degrades(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """模型不可加载（未缓存且离线）→ RuntimeError → 降级而非抛错。

        注入 HF_HUB_OFFLINE 避免联网下载挂起，令模型加载快速失败。
        """
        monkeypatch.setenv("HF_HUB_OFFLINE", "1")
        monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
        reranker = BGEReranker()  # 无 score_fn，走 FlagEmbedding 路径
        ranked = await reranker.rerank("q", _docs(2), top_k=2)
        assert reranker.last_degraded
        assert len(ranked) == 2

    @pytest.mark.asyncio
    async def test_scoring_exception_degrades(self) -> None:
        def bad_fn(pairs: list[list[str]]) -> list[float]:
            raise RuntimeError("scoring failed")

        reranker = BGEReranker(score_fn=bad_fn)
        ranked = await reranker.rerank("q", _docs(2), top_k=2)
        assert reranker.last_degraded
        assert len(ranked) == 2


class TestEventLoopNotBlocked:
    """并发压测不阻塞事件循环（铁律 1）。"""

    @pytest.mark.asyncio
    async def test_heartbeat_ticks_during_concurrent_rerank(self) -> None:
        """rerank 并发执行期间，事件循环心跳任务仍能推进。"""

        def cpu_fn(pairs: list[list[str]]) -> list[float]:
            time.sleep(0.1)  # 模拟同步推理（在 executor 线程）
            return [0.5] * len(pairs)

        reranker = BGEReranker(score_fn=cpu_fn, timeout_s=5.0)
        ticks = 0

        async def heartbeat() -> None:
            nonlocal ticks
            for _ in range(5):
                await asyncio.sleep(0.03)
                ticks += 1

        # 3 路并发 rerank + 心跳（semaphore=1 串行，但不阻塞循环）
        results = await asyncio.gather(
            reranker.rerank("q", _docs(2), 2),
            reranker.rerank("q", _docs(2), 2),
            reranker.rerank("q", _docs(2), 2),
            heartbeat(),
        )
        assert ticks == 5  # 事件循环未被阻塞
        for r in results[:3]:
            assert len(r) == 2
