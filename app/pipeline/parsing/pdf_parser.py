"""
PDF 解析器（架构 P2 · 单元 1.2）。

pypdf 文本提取；损坏/加密 PDF 容错——不崩溃，抛出明确的
ValueError（07 §5 损坏 PDF 容错用例）。OCR 兜底为后续扩展项。
"""

# --- 标准库 ---
import io
from typing import Any

# --- 第三方库 ---
from pypdf import PdfReader
from pypdf.errors import PdfReadError

# --- 本地模块 ---
from app.core.models import ParsedDocument, RawDocument, StructureNode


class PDFParser:
    """PDF 文档解析器。

    文本模式直接从 PDF 提取嵌入文本；结构树按页生成
    （level=1，title=页码标题）。扫描件 OCR 兜底为后续扩展。

    Attributes:
        use_ocr: 是否强制启用 OCR 模式（未实现，预留）。
        ocr_language: OCR 识别语言。
        min_text_ratio: 文本覆盖率阈值（预留）。
    """

    def __init__(
        self,
        use_ocr: bool = False,
        ocr_language: str = "chi_sim+eng",
        min_text_ratio: float = 0.1,
    ) -> None:
        """初始化 PDFParser。

        Args:
            use_ocr: 是否强制启用 OCR，默认 False。
            ocr_language: OCR 语言包标识，默认中英文。
            min_text_ratio: 文本覆盖率阈值。
        """
        self.use_ocr = use_ocr
        self.ocr_language = ocr_language
        self.min_text_ratio = min_text_ratio

    def parse(self, raw_doc: RawDocument) -> ParsedDocument:
        """解析 PDF 原始文档（损坏/加密时抛明确 ValueError）。

        Args:
            raw_doc: 原始文档对象，raw_bytes 应为 PDF 文件内容。

        Returns:
            解析后的文档对象：全文文本 + 按页结构树 + format_meta。

        Raises:
            ValueError: PDF 损坏、无法读取或加密未解。
        """
        if self.use_ocr:
            # TODO: OCR 管线（渲染页面 → OCR 引擎），后续扩展
            raise NotImplementedError("OCR 模式未实现（后续扩展项）")

        pages = self._extract_text_per_page(raw_doc.raw_bytes)
        parts: list[str] = []
        nodes: list[StructureNode] = []
        for page in pages:
            nodes.append(
                StructureNode(
                    level=1,
                    title=f"第 {page['page']} 页",
                    start_offset=sum(len(p) for p in parts),
                )
            )
            parts.append(page["text"] + "\n")
        return ParsedDocument(
            doc_id=raw_doc.doc_id,
            text="\n".join(p.strip() for p in parts).strip(),
            structure_tree=nodes,
            format_meta={
                "format": "pdf",
                "page_count": len(pages),
            },
        )

    def _extract_text_per_page(self, pdf_bytes: bytes) -> list[dict[str, Any]]:
        """逐页提取 PDF 文本内容（容错包装）。

        Args:
            pdf_bytes: PDF 文件的原始字节。

        Returns:
            每页文本信息列表 [{"page": int, "text": str}, ...]。

        Raises:
            ValueError: PDF 损坏或加密无法读取。
        """
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            if reader.is_encrypted:
                try:
                    reader.decrypt("")  # 尝试空口令
                except PdfReadError as exc:
                    raise ValueError(f"PDF 加密且无法解密: {exc}") from exc
            pages: list[dict[str, Any]] = []
            for i, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except PdfReadError:
                    text = ""  # 单页损坏不阻断全文档
                pages.append({"page": i, "text": text.strip()})
            return pages
        except PdfReadError as exc:
            raise ValueError(f"PDF 损坏或无法解析: {exc}") from exc
