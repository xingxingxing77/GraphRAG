"""检索子图测试（单元 5.7 S3，07 §6 E-12 断言）。

断言：整轮缓存复用（同查询不重复检索）；开启 hitl 后 interrupt 触发；
默认 hitl 关闭；单路失败不阻塞融合。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.agent import research_subgraph as rs
from app.core.models import RetrievalResult, SourceKind


class FakeRetriever:
    """检索器替身（计数）。"""

    def __init__(self, name: str, fail: bool = False) -> None:
        """初始化替身。

        Args:
            name: 来源名。
            fail: 是否抛异常。
        """
        self.name = name
        self.fail = fail
        self.calls = 0

    async def retrieve(self, query: str, top_k: int, filters: Any = None) -> list[RetrievalResult]:
        """模拟检索。"""
        self.calls += 1
        if self.fail:
            raise RuntimeError("retriever down")
        return [
            RetrievalResult(
                result_id=f"{self.name}:{query}",
                chunk_id=None,
                content=f"{self.name} 证据",
                score=0.8,
                source=SourceKind.DENSE,
                doc_id=None,
                metadata={},
            )
        ]


def _state(**overrides: Any) -> dict[str, Any]:
    """构造最小状态。"""
    state: dict[str, Any] = {
        "query": "清蒸鲈鱼",
        "retrieved_evidence": [],
        "retrieval_rounds": 0,
    }
    state.update(overrides)
    return state


@pytest.fixture(autouse=True)
def _reset_cache() -> Any:
    """每个用例清空整轮缓存。"""
    rs.clear_round_cache()
    yield
    rs.clear_round_cache()


class TestRoundCacheReuse:
    """B5 整轮缓存复用（E-12）。"""

    @pytest.mark.asyncio
    async def test_same_query_reuses_round(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = FakeRetriever("dense")

        async def fake_hub() -> dict[str, Any]:
            return {"dense": fake}

        monkeypatch.setattr(rs, "_get_retriever_hub", fake_hub)
        u1 = await rs.research_subgraph(_state())
        # 第二轮携带 u1 状态（模拟图内状态累积）
        u2 = await rs.research_subgraph(
            _state(
                retrieved_evidence=u1["retrieved_evidence"],
                retrieval_rounds=u1["retrieval_rounds"],
            )
        )
        assert fake.calls == 1  # 第二次整轮复用，不重复检索
        assert u1["retrieval_rounds"] == 1
        assert u2["retrieval_rounds"] == 2  # 轮次仍计数
        assert len(u2["retrieved_evidence"]) == 1  # 去重后不膨胀

    @pytest.mark.asyncio
    async def test_single_route_failure_not_blocking(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ok = FakeRetriever("dense")
        bad = FakeRetriever("web", fail=True)

        async def fake_hub() -> dict[str, Any]:
            return {"dense": ok, "web": bad}

        monkeypatch.setattr(rs, "_get_retriever_hub", fake_hub)
        updates = await rs.research_subgraph(_state())
        assert len(updates["retrieved_evidence"]) == 1  # 失败路不阻塞


class TestHitlInterrupt:
    """E2 HITL 挂点（开关默认 false）。"""

    def test_hitl_default_off(self) -> None:
        assert rs._hitl_enabled() is False

    @pytest.mark.asyncio
    async def test_hitl_enabled_triggers_interrupt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """开启 hitl 后挂点触发中断。

        图内执行时抛 GraphInterrupt（暂停等待 resume）；图外直调时
        langgraph interrupt() 因缺 runnable 上下文抛 RuntimeError，
        两者均证明挂点在检索前生效。
        """
        from langgraph.errors import GraphInterrupt

        monkeypatch.setattr(rs, "_hitl_enabled", lambda: True)
        with pytest.raises((GraphInterrupt, RuntimeError)):
            await rs.research_subgraph(_state())

    @pytest.mark.asyncio
    async def test_hitl_disabled_no_interrupt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rs, "_hitl_enabled", lambda: False)

        async def fake_hub() -> dict[str, Any]:
            return {"dense": FakeRetriever("dense")}

        monkeypatch.setattr(rs, "_get_retriever_hub", fake_hub)
        updates = await rs.research_subgraph(_state())
        assert updates["retrieval_rounds"] == 1
