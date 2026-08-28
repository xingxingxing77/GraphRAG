"""记忆读写节点与图拓扑测试（单元 8.1/8.3 S3，07 §6 E-05 断言）。"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
import app.agent.nodes.load_memory as lm
import app.agent.nodes.write_back as wb
from app.agent.graph import build_agent_graph
from app.agent.routers import NODE_LOAD_MEMORY, NODE_WRITE_BACK
from app.memory.scheduler import MemoryContext
from app.memory.semantic_cache import L1Entry
from tests.test_memory.conftest import FakeEmbedder, FakeQdrant, FakeRedis


class _FakeStack:
    """MemoryStack 测试替身（仅节点实际消费的面）。"""

    def __init__(self) -> None:
        from app.memory.working_memory import WorkingMemory
        from app.memory.episodic import EpisodicMemory
        from app.memory.scheduler import MemoryScheduler
        from app.memory.semantic_cache import SemanticCache

        embedder = FakeEmbedder()
        self.qdrant = FakeQdrant()
        self.redis = FakeRedis()
        self.working_memory = WorkingMemory(self.redis)
        self.episodic = EpisodicMemory(self.qdrant, embedder)
        self.scheduler = MemoryScheduler(self.working_memory, self.episodic, embedder)
        self.semantic_cache = SemanticCache(self.qdrant, embedder, self.redis)
        self.injected: MemoryContext | None = None


@pytest.fixture
def stack(monkeypatch: pytest.MonkeyPatch) -> _FakeStack:
    fake = _FakeStack()

    async def _get_stack() -> _FakeStack:
        return fake

    # 节点在函数体内 `from app.api.deps import get_memory_stack`，
    # 因此补丁必须落在源模块属性上
    monkeypatch.setattr("app.api.deps.get_memory_stack", _get_stack)
    return fake


class TestLoadMemoryNode:

    async def test_injects_context_before_query(self, stack: _FakeStack) -> None:
        await stack.working_memory.add_exchange("s1", "鲈鱼怎么蒸", "蒸8分钟")

        async def fake_build(user_id: str, session_id: str, current_query: str) -> MemoryContext:
            stack.injected = MemoryContext(
                injected_working_turns=1,
                context_text=f"[历史1轮]\nQ: 鲈鱼怎么蒸\nA: 蒸8分钟",
            )
            return stack.injected

        stack.scheduler.build_context = fake_build  # type: ignore[method-assign]
        # C1：真实 run 入参只带 original_query（不传 query）
        result = await lm.load_memory_node(
            {"original_query": "火候几分熟", "session_id": "s1", "user_id": "u1"}
        )
        assert result["query"].startswith("[历史1轮]")
        assert result["query"].endswith("火候几分熟")
        assert result["history_context"] == "[历史1轮]\nQ: 鲈鱼怎么蒸\nA: 蒸8分钟"

    async def test_no_memory_writes_back_original_query(
        self, stack: _FakeStack
    ) -> None:
        """C1：无记忆也写回 query=original_query，冲掉 checkpoint 残留。"""
        result = await lm.load_memory_node(
            {
                "query": "上一轮的旧改写查询",
                "original_query": "q",
                "session_id": "s",
            }
        )
        assert result["query"] == "q"
        assert result["history_context"] == ""
        # run 级字段每 run 清零（防上一轮终态经 checkpoint 泄漏）
        assert result["answer"] == ""
        assert result["correction_hint"] == ""
        assert result["self_correction_retries"] == 0

    async def test_failure_degrades_to_passthrough(
        self, stack: _FakeStack, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("memory down")

        monkeypatch.setattr(stack.scheduler, "build_context", boom)
        # D5：注入失败原样放行，不抛错；上报 no-memory 降级原因（9.1/E-09）
        assert await lm.load_memory_node({"query": "q", "session_id": "s"}) == {
            "degraded_reasons": ["no-memory"]
        }


class TestWriteBackNode:

    async def test_writes_all_three_on_first_turn(self, stack: _FakeStack) -> None:
        state = {
            "answer": "蒸8分钟",
            "original_query": "鲈鱼怎么蒸",
            "session_id": "s1",
            "user_id": "u1",
            "degraded": False,
            "citations": [],
            "retrieved_evidence": [],
            "latency_tier": "fast",
            "token_usage": [],
        }
        await wb.write_back_node(state)
        assert len(await stack.working_memory.get_history("s1")) == 1
        assert stack.qdrant.count("rag_episodic") == 1
        # 首轮未个性化 → L1 已回填
        assert (await stack.semantic_cache.get_l1("鲈鱼怎么蒸")).hit is True

    async def test_multi_turn_skips_cache_but_writes_memory(
        self, stack: _FakeStack
    ) -> None:
        base: dict[str, Any] = {
            "answer": "a",
            "original_query": "q",
            "session_id": "s1",
            "user_id": "u1",
            "degraded": False,
            "citations": [],
            "retrieved_evidence": [],
            "latency_tier": "fast",
            "token_usage": [],
        }
        await wb.write_back_node(dict(base, original_query="第一问", answer="答一"))
        await wb.write_back_node(dict(base, original_query="第二问", answer="答二"))
        history = await stack.working_memory.get_history("s1")
        assert len(history) == 2
        assert stack.qdrant.count("rag_episodic") == 2
        lookup = await stack.semantic_cache.get_l1("第二问")
        # H2：多轮含个性化上下文 → 不入缓存
        assert lookup.hit is False

    async def test_degraded_answer_skips_everything(self, stack: _FakeStack) -> None:
        await wb.write_back_node(
            {"answer": "降级答案", "session_id": "s1", "degraded": True}
        )
        assert await stack.working_memory.get_history("s1") == []
        assert stack.qdrant.count("rag_episodic") == 0

    async def test_matched_doc_ids_extracted_from_evidence(
        self, stack: _FakeStack
    ) -> None:
        evidence = [{"metadata": {"doc_id": "doc-9"}}]
        await wb.write_back_node(
            {
                "answer": "a",
                "original_query": "q9",
                "session_id": "s-fresh",
                "user_id": "u1",
                "degraded": False,
                "citations": [],
                "retrieved_evidence": evidence,
                "latency_tier": "standard",
                "token_usage": [],
            }
        )
        payloads = [
            rec["payload"]
            for rec in stack.qdrant.points["rag_cache"].values()
        ]
        assert any(p["matched_doc_ids"] == ["doc-9"] for p in payloads)

    async def test_matched_doc_ids_reads_top_level_doc_id(
        self, stack: _FakeStack
    ) -> None:
        """M5：fulltext 路的 doc_id 在顶层字段而非 metadata。"""
        evidence = [{"doc_id": "doc-ft", "metadata": {"entity_id": "e1"}}]
        await wb.write_back_node(
            {
                "answer": "a",
                "original_query": "q",
                "session_id": "s-ft",
                "user_id": "u1",
                "degraded": False,
                "citations": [],
                "retrieved_evidence": evidence,
                "latency_tier": "standard",
                "token_usage": [],
            }
        )
        payloads = [
            rec["payload"]
            for rec in stack.qdrant.points["rag_cache"].values()
        ]
        assert any(p["matched_doc_ids"] == ["doc-ft"] for p in payloads)


class TestGraphTopology:

    def test_load_memory_is_entry_and_write_back_precedes_end(self) -> None:
        graph = build_agent_graph()
        nodes = graph.get_graph().nodes
        assert NODE_LOAD_MEMORY in nodes
        assert NODE_WRITE_BACK in nodes

    def test_injection_point_before_planner(self) -> None:
        """注入在改写前（04 §4/J17）：load_memory → query_understanding → planner。"""
        graph = build_agent_graph()
        edges = {
            (e.source, e.target) for e in graph.get_graph().edges
        }
        assert ("__start__", NODE_LOAD_MEMORY) in edges
        assert (NODE_LOAD_MEMORY, "query_understanding") in edges
        assert ("query_understanding", "planner") in edges
