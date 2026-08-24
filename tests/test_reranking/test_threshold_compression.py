"""阈值过滤与可插拔压缩测试（单元 4.2 S3，07 §5 断言）。

断言：阈值边界用例（边界含）；llm_extract/extractive/none 切换生效；
证据选择准出（数量 ≤ Top-K 且含分数）。
"""

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import RetrievalResult, SourceKind
from app.reranking.context_compressor import (
    ContextCompressor,
    ExtractiveStrategy,
    LLMExtractStrategy,
    NoneStrategy,
    create_strategy,
)
from app.reranking.scoring import select_evidence


def _mk(rid: str, content: str, score: float) -> RetrievalResult:
    """构造 RetrievalResult。"""
    return RetrievalResult(
        result_id=rid,
        chunk_id=None,
        content=content,
        score=score,
        source=SourceKind.DENSE,
        doc_id=None,
        metadata={},
    )


class TestSelectEvidence:
    """阈值过滤 + Top-K 截断（准出：证据数 ≤ Top-K 且含分数）。"""

    def test_threshold_boundary_inclusive(self) -> None:
        """边界含：score == threshold 保留。"""
        reranked = [
            (_mk("a", "高分", 0.5), 0.5),
            (_mk("b", "边界", 0.3), 0.3),
            (_mk("c", "低分", 0.2), 0.2),
        ]
        kept = select_evidence(reranked, threshold=0.3, top_k=5)
        assert [d.result_id for d, _ in kept] == ["a", "b"]

    def test_top_k_truncation_with_scores(self) -> None:
        reranked = [(_mk(f"d{i}", f"c{i}", 0.9 - i * 0.1), 0.9 - i * 0.1) for i in range(8)]
        kept = select_evidence(reranked, threshold=0.0, top_k=5)
        assert len(kept) == 5
        assert all(isinstance(s, float) for _, s in kept)  # 含分数

    def test_all_below_threshold_empty(self) -> None:
        reranked = [(_mk("a", "x", 0.1), 0.1)]
        assert select_evidence(reranked, threshold=0.3, top_k=5) == []


class TestStrategySwitch:
    """三策略切换生效断言（J11）。"""

    @pytest.mark.asyncio
    async def test_none_strategy_passthrough(self) -> None:
        results = [_mk("a", "完整内容不压缩", 0.9)]
        out = await ContextCompressor(NoneStrategy()).compress("q", results)
        assert out[0].content == "完整内容不压缩"

    @pytest.mark.asyncio
    async def test_extractive_picks_relevant_sentences(self) -> None:
        content = "清蒸鲈鱼是一道粤菜。今天天气不错。鲈鱼需要蒸八分钟。"
        results = [_mk("a", content, 0.9)]
        out = await ContextCompressor(ExtractiveStrategy(max_sentences=2)).compress(
            "清蒸鲈鱼", results
        )
        assert "清蒸鲈鱼是一道粤菜" in out[0].content
        assert "今天天气不错" not in out[0].content  # 无关句被剔除

    @pytest.mark.asyncio
    async def test_llm_extract_uses_injected_fn(self) -> None:
        async def fake_extract(query: str, content: str) -> str:
            return f"提取:{query}"

        strategy = LLMExtractStrategy(fake_extract)
        results = [_mk("a", "原始长内容", 0.9)]
        out = await ContextCompressor(strategy).compress("鲈鱼", results)
        assert out[0].content == "提取:鲈鱼"

    @pytest.mark.asyncio
    async def test_llm_extract_failure_falls_back_to_original(self) -> None:
        async def bad_extract(query: str, content: str) -> str:
            raise RuntimeError("llm down")

        strategy = LLMExtractStrategy(bad_extract)
        results = [_mk("a", "原始内容", 0.9)]
        out = await ContextCompressor(strategy).compress("q", results)
        assert out[0].content == "原始内容"

    def test_create_strategy_by_name(self) -> None:
        assert create_strategy("none").name == "none"
        assert create_strategy("extractive").name == "extractive"

        async def fn(q: str, c: str) -> str:
            return c

        assert create_strategy("llm_extract", fn).name == "llm_extract"
        # llm_extract 缺 extract_fn → 回退 none
        assert create_strategy("llm_extract").name == "none"
        # 未知策略名 → none
        assert create_strategy("unknown").name == "none"
