"""P2 解析层测试（单元 1.2 S3，07 §5 断言）。

断言：各格式 structure_tree 层级/offset；损坏 PDF 容错；
目标语料（menu/HowToCook）解析通过率 100%。
"""

# --- 标准库 ---
from datetime import datetime, timezone
from pathlib import Path

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.core.models import RawDocument
from app.pipeline.parsing.html_parser import HTMLParser
from app.pipeline.parsing.markdown_parser import MarkdownParser
from app.pipeline.parsing.pdf_parser import PDFParser
from app.pipeline.parsing.router import FormatRouter

REPO_ROOT = Path(__file__).resolve().parents[2]


def _raw(content: bytes, path: str, mime: str = "text/markdown") -> RawDocument:
    return RawDocument(
        doc_id="doc-test",
        source_path=path,
        raw_bytes=content,
        mime_type=mime,
        timestamp=datetime.now(timezone.utc),
        content_hash="x" * 64,
    )


class TestMarkdownParser:
    def test_header_levels_and_offsets(self) -> None:
        md = "# 清蒸鲈鱼\n\n正文一\n\n## 操作步骤\n\n### 蒸制\n"
        doc = MarkdownParser().parse(_raw(md.encode("utf-8"), "a.md"))
        tree = doc.structure_tree
        assert [n.level for n in tree] == [1, 2, 3]
        assert [n.title for n in tree] == ["清蒸鲈鱼", "操作步骤", "蒸制"]
        # offset 单调递增且指向标题行首
        offsets = [n.start_offset for n in tree]
        assert offsets == sorted(offsets)
        assert md[offsets[0]:].startswith("# 清蒸鲈鱼")
        assert doc.format_meta["format"] == "markdown"

    def test_code_fence_headers_ignored(self) -> None:
        md = "# 真实标题\n\n```bash\n# 这是注释不是标题\n## 也不是\n```\n\n## 真实二级\n"
        doc = MarkdownParser().parse(_raw(md.encode("utf-8"), "a.md"))
        titles = [n.title for n in doc.structure_tree]
        assert titles == ["真实标题", "真实二级"]

    def test_setext_and_text_preserved(self) -> None:
        md = "# 标题\n\n保留的正文内容。\n"
        doc = MarkdownParser().parse(_raw(md.encode("utf-8"), "a.md"))
        assert "保留的正文内容" in doc.text


class TestHTMLParser:
    def test_removes_nav_script_and_extracts_headings(self) -> None:
        html = (
            "<html><head><title>页面标题</title></head><body>"
            "<nav>导航应被移除</nav>"
            "<script>var x=1;</script>"
            "<h1>主标题</h1><p>段落甲</p>"
            "<h2>次标题</h2><p>段落乙</p>"
            "</body></html>"
        )
        doc = HTMLParser().parse(_raw(html.encode("utf-8"), "a.html", "text/html"))
        assert "导航应被移除" not in doc.text
        assert "var x=1" not in doc.text
        assert "段落甲" in doc.text and "段落乙" in doc.text
        assert [(n.level, n.title) for n in doc.structure_tree] == [
            (1, "主标题"),
            (2, "次标题"),
        ]
        assert doc.format_meta.get("title") == "页面标题"


class TestPDFParser:
    def test_corrupted_pdf_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            PDFParser().parse(_raw(b"not a real pdf", "bad.pdf", "application/pdf"))

    def test_empty_bytes_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            PDFParser().parse(_raw(b"", "empty.pdf", "application/pdf"))


class TestFormatRouter:
    def test_route_by_extension(self) -> None:
        router = FormatRouter()
        assert router.route("a.md") == "markdown"
        assert router.route("a.html") == "html"
        assert router.route("a.pdf") == "pdf"

    def test_route_by_mime_priority(self) -> None:
        router = FormatRouter()
        assert router.route("noext", mime_type="application/pdf") == "pdf"

    def test_unknown_format_raises(self) -> None:
        router = FormatRouter()
        with pytest.raises(ValueError):
            router.route("a.xyz")

    @pytest.mark.asyncio
    async def test_parse_dispatch_markdown(self) -> None:
        router = FormatRouter()
        doc = await router.parse(_raw("# 标题\n正文".encode("utf-8"), "a.md"))
        assert doc.structure_tree[0].title == "标题"


class TestHowToCookCorpusParsing:
    """目标语料解析通过率 100%（准出）。"""

    def test_all_markdown_parse_success(self) -> None:
        corpus = REPO_ROOT / "menu" / "HowToCook"
        md_files = sorted(corpus.rglob("*.md"))
        assert md_files, "HowToCook 语料缺失"
        parser = MarkdownParser()
        failures: list[str] = []
        for f in md_files:
            raw = _raw(f.read_bytes(), str(f))
            try:
                doc = parser.parse(raw)
                if not doc.text.strip():
                    failures.append(f"{f}: 解析文本为空")
            except Exception as exc:  # noqa: BLE001 - 汇总失败清单
                failures.append(f"{f}: {exc}")
        assert not failures, f"解析失败 {len(failures)} 个: {failures[:5]}"
        # 通过率 100%：全部文件成功产出 ParsedDocument
        assert len(md_files) > 100
