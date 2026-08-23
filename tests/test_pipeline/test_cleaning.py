"""P3 清洗层测试（单元 1.3 S3，07 §8 断言）。

断言：规则正反例/边界（空串/超长/混合编码）；quality_score 与门控
阈值生效、脏样例被拦；样板文字清除；PII 脱敏；近似去重。
"""

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import CleanedDocument, ParsedDocument
from app.pipeline.cleaning.pipeline import build_cleaning_pipeline
from app.pipeline.cleaning.quality_gate import QualityGate, mask_pii
from app.pipeline.cleaning.rules.fix_encoding import FixEncodingRule
from app.pipeline.cleaning.rules.normalize_punctuation import NormalizePunctuationRule
from app.pipeline.cleaning.rules.normalize_whitespace import NormalizeWhitespaceRule
from app.pipeline.cleaning.rules.remove_boilerplate import RemoveBoilerplateRule
from app.pipeline.cleaning.rules.remove_image_refs import RemoveImageRefsRule


def _cleaned(text: str) -> CleanedDocument:
    return CleanedDocument(doc_id="doc-test", text=text)


def _parsed(text: str) -> ParsedDocument:
    return ParsedDocument(doc_id="doc-test", text=text)


class TestRules:
    """规则正反例与边界（07 §8）。"""

    @pytest.mark.asyncio
    async def test_remove_image_refs_positive(self) -> None:
        doc = _cleaned("# 清蒸鲈鱼\n\n![成品图](img/fish.jpg)\n\n大火蒸 8 分钟")
        out = await RemoveImageRefsRule().process(doc, {})
        assert "![" not in out.text
        assert "大火蒸 8 分钟" in out.text

    @pytest.mark.asyncio
    async def test_remove_image_refs_keeps_hyperlinks(self) -> None:
        doc = _cleaned("参考 [链接](http://a.b/c) 与 ![图](x.png)")
        out = await RemoveImageRefsRule().process(doc, {})
        assert "[链接](http://a.b/c)" in out.text
        assert "![" not in out.text

    @pytest.mark.asyncio
    async def test_remove_boilerplate_config_patterns(self) -> None:
        doc = _cleaned("# 菜谱\n\n请提出 Issue 或 Pull request\n\n正文内容")
        out = await RemoveBoilerplateRule().process(
            doc, {"patterns": ["请提出 Issue 或 Pull request", "贡献指南"]}
        )
        assert "请提出 Issue 或 Pull request" not in out.text
        assert "正文内容" in out.text

    @pytest.mark.asyncio
    async def test_normalize_whitespace_compresses_newlines(self) -> None:
        doc = _cleaned("段落一\n\n\n\n\n\n段落二")
        out = await NormalizeWhitespaceRule().process(doc, {})
        assert "\n\n\n" not in out.text
        assert "段落一\n\n段落二" == out.text

    @pytest.mark.asyncio
    async def test_normalize_whitespace_empty_string_boundary(self) -> None:
        out = await NormalizeWhitespaceRule().process(_cleaned(""), {})
        assert out.text == ""

    @pytest.mark.asyncio
    async def test_fix_encoding_removes_replacement_and_control_chars(self) -> None:
        doc = _cleaned("正常文本\ufffd\u0001尾部")
        out = await FixEncodingRule().process(doc, {})
        assert "\ufffd" not in out.text
        assert "\u0001" not in out.text
        assert "正常文本" in out.text

    @pytest.mark.asyncio
    async def test_normalize_punctuation_nfc(self) -> None:
        doc = _cleaned(" café ")  # e + ́ 组合字符
        out = await NormalizePunctuationRule().process(doc, {"target_form": "NFC"})
        assert "café" in out.text

    @pytest.mark.asyncio
    async def test_punctuation_invalid_form_falls_back_nfc(self) -> None:
        out = await NormalizePunctuationRule().process(
            _cleaned("文本"), {"target_form": "BOGUS"}
        )
        assert out.text == "文本"


class TestQualityGate:
    """门控阈值生效，脏样例被拦（07 §8）。"""

    def test_short_text_blocked(self) -> None:
        gate = QualityGate(min_length=20)
        report = gate.check(_cleaned("太短"))
        assert report.is_valid is False
        assert report.quality_score < 1.0
        assert any("长度" in r for r in report.reasons)

    def test_long_zh_text_passes(self) -> None:
        gate = QualityGate(min_length=20)
        text = "清蒸鲈鱼的做法：先处理鲈鱼，去鳞去内脏，水开后大火蒸八分钟。"
        report = gate.check(_cleaned(text))
        assert report.is_valid is True
        assert report.quality_score == 1.0

    def test_pii_masking(self) -> None:
        masked, hits = mask_pii("联系电话 13812345678，邮箱 a@b.com")
        assert "13812345678" not in masked
        assert "***" in masked
        assert hits >= 2

    def test_near_duplicate_detected(self) -> None:
        gate = QualityGate(min_length=10, dedup_threshold=0.9)
        text = "宫保鸡丁：鸡胸肉切丁腌制，花生米炸脆，快炒出锅，酸甜微辣。"
        gate.register(text)
        report = gate.check(_cleaned(text))  # 完全相同必触发
        assert report.is_valid is False
        assert any("近似重复" in r for r in report.reasons)


class TestCleaningPipeline:
    """规则链编排与 cleaned_meta（05 §5.6）。"""

    @pytest.mark.asyncio
    async def test_build_from_yaml_and_run(self) -> None:
        pipeline = build_cleaning_pipeline()
        assert pipeline.rule_names == [
            "RemoveImageRefs",
            "RemoveBoilerplate",
            "NormalizeWhitespace",
            "FixEncoding",
            "NormalizePunctuation",
        ]
        text = (
            "# 清蒸鲈鱼\n\n![图](a.jpg)\n\n"
            "请提出 Issue 或 Pull request\n\n"
            "水开后大火蒸 8 分钟，淋上蒸鱼豉油即可上桌。"
        )
        cleaned = await pipeline.run(_parsed(text))
        assert "![" not in cleaned.text
        assert "请提出 Issue 或 Pull request" not in cleaned.text
        assert "蒸 8 分钟" in cleaned.text
        assert cleaned.cleaned_meta["applied_rules"]
        assert "quality_gate" in cleaned.cleaned_meta
        assert 0.0 <= cleaned.quality_score <= 1.0

    @pytest.mark.asyncio
    async def test_dirty_sample_blocked_by_gate(self) -> None:
        pipeline = build_cleaning_pipeline()
        cleaned = await pipeline.run(_parsed("短"))
        assert cleaned.cleaned_meta["quality_gate"]["is_valid"] is False
        assert cleaned.quality_score < 1.0

    @pytest.mark.asyncio
    async def test_pii_masked_in_pipeline(self) -> None:
        pipeline = build_cleaning_pipeline()
        text = "预约电话 13912345678。清蒸鲈鱼需要蒸制八分钟，火候是关键步骤。"
        cleaned = await pipeline.run(_parsed(text))
        assert "13912345678" not in cleaned.text
        assert cleaned.cleaned_meta["pii_masked"] >= 1
