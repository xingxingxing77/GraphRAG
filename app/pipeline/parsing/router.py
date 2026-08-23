"""
格式路由器（架构 P2 格式路由 · 单元 1.2）。

按 MIME type / 扩展名将 RawDocument 分发到对应解析器
（markdown / html / pdf）。
"""

# --- 标准库 ---
import mimetypes
from typing import Protocol

# --- 本地模块 ---
from app.core.models import ParsedDocument, RawDocument
from app.pipeline.parsing.html_parser import HTMLParser
from app.pipeline.parsing.markdown_parser import MarkdownParser
from app.pipeline.parsing.pdf_parser import PDFParser


class _Parser(Protocol):
    """解析器结构协议：parse(RawDocument) -> ParsedDocument。"""

    def parse(self, raw_doc: RawDocument) -> ParsedDocument: ...

# MIME type 到解析器名称的映射（默认）
_MIME_ROUTER_MAP: dict[str, str] = {
    "text/markdown": "markdown",
    "text/x-markdown": "markdown",
    "text/html": "html",
    "application/pdf": "pdf",
}

# 扩展名到解析器名称的映射（兜底）
_EXT_ROUTER_MAP: dict[str, str] = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
    ".pdf": "pdf",
}


class FormatRouter:
    """格式路由器。

    根据文档的 MIME type 或文件扩展名，决定应使用哪个解析器处理。

    Attributes:
        mime_map: 自定义 MIME type → 解析器名称映射。
        ext_map: 自定义扩展名 → 解析器名称映射。
    """

    def __init__(
        self,
        mime_map: dict[str, str] | None = None,
        ext_map: dict[str, str] | None = None,
    ) -> None:
        """初始化 FormatRouter。

        Args:
            mime_map: 自定义 MIME type 到解析器名称的映射。
            ext_map: 自定义扩展名到解析器名称的映射。
        """
        self.mime_map: dict[str, str] = mime_map or dict(_MIME_ROUTER_MAP)
        self.ext_map: dict[str, str] = ext_map or dict(_EXT_ROUTER_MAP)
        self._parsers: dict[str, _Parser] = {
            "markdown": MarkdownParser(),
            "html": HTMLParser(),
            "pdf": PDFParser(),
        }

    def route(self, file_path: str, mime_type: str | None = None) -> str:
        """根据 MIME / 文件路径返回解析器名称。

        优先 MIME type，无法识别时退回扩展名。

        Args:
            file_path: 文件路径。
            mime_type: 已知 MIME type（可选，优先使用）。

        Returns:
            解析器名称："markdown" / "html" / "pdf"。

        Raises:
            ValueError: 无法识别文件格式。
        """
        if mime_type and mime_type in self.mime_map:
            return self.mime_map[mime_type]
        guessed = mimetypes.guess_type(file_path)[0]
        if guessed and guessed in self.mime_map:
            return self.mime_map[guessed]
        ext = "." + file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        if ext in self.ext_map:
            return self.ext_map[ext]
        raise ValueError(f"无法识别文件格式: {file_path} (mime={mime_type})")

    async def parse(self, raw_doc: RawDocument) -> ParsedDocument:
        """路由并调用对应解析器处理原始文档。

        Args:
            raw_doc: 原始文档对象。

        Returns:
            解析后的文档对象。

        Raises:
            ValueError: 无法识别文档格式。
        """
        name = self.route(raw_doc.source_path, raw_doc.mime_type)
        parser = self._parsers[name]
        return parser.parse(raw_doc)
