"""P5 增强层测试（单元 2.2 S3，07 §5 断言）。

断言：关键词抽测；J15 白名单打底 + 访问计数叠加并集逻辑；
元数据键规范补全（架构 §3.2）。
"""

# --- 标准库 ---
from pathlib import Path

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import Chunk, EnrichedChunk, MetadataKeys, PositionMeta
from app.pipeline.enrichment.metadata_enricher import MetadataEnricher, enrich_chunks
from app.pipeline.enrichment.semantic_enricher import (
    HighValueFilter,
    KeywordExtractor,
    SemanticEnricher,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _chunk(content: str, doc_id: str = "doc-e", seq: int = 0) -> Chunk:
    return Chunk(
        chunk_id=f"{doc_id}-{seq}",
        doc_id=doc_id,
        seq=seq,
        content=content,
        title_path=["清蒸鲈鱼"],
        position=PositionMeta(start_char=0, end_char=len(content)),
    )


class TestMetadataEnricher:
    """元数据键补全与推断。"""

    def test_required_keys_populated(self) -> None:
        enricher = MetadataEnricher()
        enriched = enricher.enrich(
            _chunk("内容"), "menu/HowToCook/dishes/aquatic/清蒸鲈鱼/清蒸鲈鱼.md",
            quality_score=0.95, lang="zh",
        )
        md = enriched.chunk.metadata
        assert md[MetadataKeys.DOC_ID] == "doc-e"
        assert md[MetadataKeys.CHUNK_ID] == "doc-e-0"
        assert md[MetadataKeys.SOURCE].endswith("清蒸鲈鱼.md")
        assert md[MetadataKeys.DOC_TYPE] == "recipes"
        assert md[MetadataKeys.CATEGORY] == "aquatic"
        assert md[MetadataKeys.QUALITY_SCORE] == 0.95
        assert md[MetadataKeys.LANG] == "zh"
        assert md[MetadataKeys.CREATED_AT]

    def test_doc_type_inference(self) -> None:
        enricher = MetadataEnricher()
        assert enricher.infer_doc_type("a/dishes/x/y.md") == "recipes"
        assert enricher.infer_doc_type("a\\dishes\\x\\y.md") == "recipes"
        assert enricher.infer_doc_type("a/tips/learn/x.md") == "tips"
        assert enricher.infer_doc_type("other/readme.md") == "knowledge"

    def test_category_inference(self) -> None:
        enricher = MetadataEnricher()
        assert enricher.infer_category("menu/dishes/meat_dish/红烧肉/红烧肉.md") == "meat_dish"
        assert enricher.infer_category("menu/tips/learn/刀工.md") == "learn"
        assert enricher.infer_category("menu/other.md") == "uncategorized"


class TestKeywordExtractor:
    """关键词抽测（07 §5）。"""

    def test_frequent_terms_ranked_first(self) -> None:
        text = "鲈鱼处理干净。鲈鱼两面划刀。鲈鱼放入盘中。大火蒸八分钟。"
        keywords = KeywordExtractor().extract(text)
        assert keywords, "应提取出关键词"
        assert keywords[0] == "鲈鱼"  # 最高频

    def test_stopwords_and_short_tokens_filtered(self) -> None:
        text = "可以 可以 加入 加入 a 单字 鲈鱼 鲈鱼 蒸制 蒸制"
        keywords = KeywordExtractor().extract(text)
        assert "可以" not in keywords
        assert "加入" not in keywords
        assert "鲈鱼" in keywords

    def test_top_k_limit(self) -> None:
        text = "甲乙丙丁戊己庚辛壬癸 " * 5
        keywords = KeywordExtractor(top_k=3).extract(text)
        assert len(keywords) <= 3

    def test_empty_text(self) -> None:
        assert KeywordExtractor().extract("") == []


class TestHighValueFilter:
    """J15：白名单打底 + 访问计数叠加，并集生效（07 §5）。"""

    def test_whitelist_hit_without_access_count(self) -> None:
        f = HighValueFilter(categories=["staple", "meat_dish"], min_access_count=10)
        assert f.is_high_value("meat_dish", access_count=0) is True

    def test_access_count_overlay_without_whitelist(self) -> None:
        f = HighValueFilter(categories=["staple"], min_access_count=10)
        assert f.is_high_value("aquatic", access_count=10) is True
        assert f.is_high_value("aquatic", access_count=9) is False

    def test_union_of_both_mechanisms(self) -> None:
        f = HighValueFilter(categories=["staple"], min_access_count=10)
        # 两套机制都不命中
        assert f.is_high_value("aquatic", access_count=3) is False
        # 任一命中即高价值（并集）
        assert f.is_high_value("staple", access_count=0) is True
        assert f.is_high_value("dessert", access_count=42) is True

    def test_empty_whitelist_cold_start(self) -> None:
        f = HighValueFilter(categories=[], min_access_count=10)
        assert f.is_high_value("staple", access_count=0) is False


class TestSemanticEnricher:
    """编排：关键词写入 EnrichedChunk。"""

    @pytest.mark.asyncio
    async def test_enrich_fills_keywords(self) -> None:
        enriched = EnrichedChunk(chunk=_chunk("鲈鱼 鲈鱼 蒸制 蒸制 火候"))
        out = await SemanticEnricher().enrich(enriched)
        assert "鲈鱼" in out.keywords

    @pytest.mark.asyncio
    async def test_enrich_chunks_orchestrator_on_corpus(self) -> None:
        corpus_file = (
            REPO_ROOT / "menu" / "HowToCook" / "dishes" / "aquatic" / "清蒸鲈鱼" / "清蒸鲈鱼.md"
        )
        assert corpus_file.exists(), "清蒸鲈鱼语料缺失"
        text = corpus_file.read_text(encoding="utf-8")
        chunks = [_chunk(text[:800])]
        results = await enrich_chunks(
            chunks, str(corpus_file), quality_score=1.0, lang="zh"
        )
        assert len(results) == 1
        assert results[0].keywords, "语料应提取出关键词"
        assert results[0].chunk.metadata[MetadataKeys.DOC_TYPE] == "recipes"
