"""P4 分块层测试（单元 2.1 S3，07 §8 断言）。

断言：边界用例（空标题树 / 超长段落 / min_size 过滤）；
chunk_size/overlap 约束；title_path 与 position 精确性；
上下文保留（前缀注入 / parent_ref）；真实语料分块跑通。
"""

# --- 标准库 ---
from pathlib import Path

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import CleanedDocument
from app.pipeline.chunking.markdown_splitter import MarkdownHeaderSplitter
from app.pipeline.chunking.recursive_splitter import RecursiveCharacterSplitter
from app.pipeline.chunking.strategy import (
    HierarchicalChunkingStrategy,
    chunk_document,
)
from app.pipeline.config import load_pipeline_config

REPO_ROOT = Path(__file__).resolve().parents[2]


def _doc(text: str, doc_id: str = "doc-test") -> CleanedDocument:
    return CleanedDocument(doc_id=doc_id, text=text)


class TestMarkdownHeaderSplitter:
    """标题切分与 title_path。"""

    def test_title_path_hierarchy(self) -> None:
        md = "# 清蒸鲈鱼\n\n简介\n\n## 操作步骤\n\n### 蒸制\n\n大火蒸 8 分钟\n"
        sections = MarkdownHeaderSplitter().split(md)
        paths = [s.title_path for s in sections]
        assert ["清蒸鲈鱼"] in paths
        assert ["清蒸鲈鱼", "操作步骤"] in paths
        assert ["清蒸鲈鱼", "操作步骤", "蒸制"] in paths

    def test_no_headings_single_root_section(self) -> None:
        sections = MarkdownHeaderSplitter().split("没有标题的纯文本段落。")
        assert len(sections) == 1
        assert sections[0].title_path == []
        assert sections[0].text == "没有标题的纯文本段落。"

    def test_section_offsets_cover_full_text(self) -> None:
        md = "# A\n\n甲\n\n## B\n\n乙\n"
        sections = MarkdownHeaderSplitter().split(md)
        # 各节切片拼接 == 全文（无重叠无遗漏）
        assert "".join(s.text for s in sections) == md


class TestRecursiveCharacterSplitter:
    """字符级兜底约束。"""

    def test_chunks_within_size_and_cover_text(self) -> None:
        text = "。".join(f"第{i}句话内容填充" for i in range(200))
        splitter = RecursiveCharacterSplitter(chunk_size=200, chunk_overlap=40)
        spans = splitter.split_spans(text)
        assert spans, "应产出至少一个块"
        for start, end in spans:
            assert end - start <= 240  # chunk_size + 容忍（overlap 回退不超容量一半）
        # 覆盖完整：首块从 0 起，末块至 len(text)
        assert spans[0][0] == 0
        assert spans[-1][1] == len(text)

    def test_overlap_between_adjacent_chunks(self) -> None:
        text = "。".join(f"句子{i}的内容" for i in range(100))
        splitter = RecursiveCharacterSplitter(chunk_size=100, chunk_overlap=20)
        spans = splitter.split_spans(text)
        assert len(spans) >= 2
        prev_end = spans[0][1]
        next_start = spans[1][0]
        assert next_start < prev_end  # 存在重叠
        assert prev_end - next_start <= 20

    def test_empty_text_returns_no_spans(self) -> None:
        assert RecursiveCharacterSplitter().split_spans("") == []


class TestHierarchicalStrategy:
    """多级策略与边界用例（07 §8）。"""

    @pytest.mark.asyncio
    async def test_structured_doc_keeps_sections(self) -> None:
        md = "# 菜谱\n\n" + "步骤说明。" * 10 + "\n\n## 小贴士\n\n" + "技巧内容。" * 10
        strategy = HierarchicalChunkingStrategy()
        chunks = await strategy.split(_doc(md), {})
        assert len(chunks) >= 2
        # 每块 position 精确：content == text[start:end]
        for c in chunks:
            assert md[c.position.start_char : c.position.end_char] == c.content
            assert c.chunk_id == f"doc-test-{c.seq}"

    @pytest.mark.asyncio
    async def test_empty_heading_tree_falls_back(self) -> None:
        text = "没有标题的长文。" * 200  # 空标题树 + 超长
        strategy = HierarchicalChunkingStrategy()
        chunks = await strategy.split(_doc(text), {})
        assert len(chunks) > 1  # 触发字符级兜底
        for c in chunks:
            assert len(c.content) <= 1500

    @pytest.mark.asyncio
    async def test_oversized_single_section_is_split(self) -> None:
        md = "# 超长章节\n\n" + "这是一个超长的段落句子。" * 300
        strategy = HierarchicalChunkingStrategy()
        chunks = await strategy.split(_doc(md), {})
        assert len(chunks) > 1
        for c in chunks:
            assert c.title_path == ["超长章节"]  # 继承标题路径
            assert len(c.content) <= 1500

    @pytest.mark.asyncio
    async def test_min_size_filter(self) -> None:
        md = "# 正常章节\n\n" + "足够长的内容填充。" * 20 + "\n\n## 短节\n\n太短"
        strategy = HierarchicalChunkingStrategy(min_chunk_size=50)
        chunks = await strategy.split(_doc(md), {})
        for c in chunks:
            assert len(c.content.strip()) >= 50

    @pytest.mark.asyncio
    async def test_empty_document_returns_no_chunks(self) -> None:
        chunks = await HierarchicalChunkingStrategy().split(_doc(""), {})
        assert chunks == []


class TestChunkDocumentOrchestrator:
    """编排入口与上下文保留。"""

    @pytest.mark.asyncio
    async def test_prefix_injection_and_parent_ref(self) -> None:
        md = "# 清蒸鲈鱼\n\n## 蒸制\n\n" + "大火蒸八分钟，火候是关键步骤。" * 10
        chunks = await chunk_document(_doc(md, doc_id="doc-9"))
        assert chunks
        for c in chunks:
            assert c.metadata.get("parent_ref") == "doc-9"
            if c.title_path:
                assert c.content.startswith("[")  # 标题路径前缀已注入

    @pytest.mark.asyncio
    async def test_loads_config_from_yaml(self) -> None:
        cfg = load_pipeline_config().pipeline.chunking
        assert cfg.strategy == "hierarchical"
        assert cfg.second_level.chunk_size == 500
        assert cfg.constraints.min_chunk_size == 50


class TestHowToCookChunking:
    """真实语料分块跑通。"""

    @pytest.mark.asyncio
    async def test_corpus_sample_chunks_valid(self) -> None:
        sample = REPO_ROOT / "menu" / "HowToCook" / "dishes" / "aquatic" / "清蒸鲈鱼"
        md_files = sorted(sample.rglob("*.md"))
        assert md_files, "清蒸鲈鱼语料缺失"
        text = md_files[0].read_text(encoding="utf-8")
        chunks = await chunk_document(_doc(text, doc_id="doc-corpus"))
        assert chunks, "应产出至少一个 chunk"
        for c in chunks:
            assert c.content.strip()
            assert c.position.end_char > c.position.start_char
            assert len(c.content) <= 1500 + 200  # 前缀注入后的宽松上限
