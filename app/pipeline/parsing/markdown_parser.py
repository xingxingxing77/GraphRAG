"""
Markdown 解析器（架构 P2 · 单元 1.2）。

解析 Markdown 文档，提取 ATX 标题层级树（StructureNode 扁平序列），
围栏代码块内的伪标题不参与结构提取；保留正文全文供后续清洗/分块。
"""

# --- 标准库 ---
import re

# --- 本地模块 ---
from app.core.models import ParsedDocument, RawDocument, StructureNode
from app.pipeline.ingestion.loader import decode_text


class MarkdownParser:
    """Markdown 文档解析器。

    Attributes:
        header_pattern: 匹配 ATX 标题的正则表达式。
    """

    # 匹配 ATX 标题：# ~ ###### 开头
    header_pattern: re.Pattern[str] = re.compile(
        r"^(?P<level>#{1,6})\s+(?P<title>.+?)\s*#*\s*$"
    )

    def parse(self, raw_doc: RawDocument) -> ParsedDocument:
        """解析 Markdown 原始文档。

        处理流程：
        1. raw_bytes 多编码容错解码。
        2. 逐行扫描提取标题层级树（跳过围栏代码块内伪标题）。
        3. 组装 ParsedDocument（text 保留全文，清洗交由 P3）。

        Args:
            raw_doc: 原始文档对象，raw_bytes 应为 Markdown 内容。

        Returns:
            解析后的文档对象，包含纯文本和标题结构树。
        """
        text, encoding = decode_text(raw_doc.raw_bytes)
        structure_tree = self._extract_structure_tree(text)
        return ParsedDocument(
            doc_id=raw_doc.doc_id,
            text=text,
            structure_tree=structure_tree,
            format_meta={
                "format": "markdown",
                "encoding": encoding,
                "line_count": text.count("\n") + 1,
            },
        )

    def _extract_structure_tree(self, text: str) -> list[StructureNode]:
        """从 Markdown 文本中提取标题层级树（扁平序列）。

        围栏代码块（``` / ~~~）内的 # 行视为内容而非标题（伪标题防护）。

        Args:
            text: Markdown 纯文本。

        Returns:
            标题节点列表，含 level/title/start_offset（字符偏移）。
        """
        nodes: list[StructureNode] = []
        in_fence = False
        fence_marker = ""
        offset = 0
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if not in_fence and (
                stripped.startswith("```") or stripped.startswith("~~~")
            ):
                in_fence = True
                fence_marker = stripped[:3]
            elif in_fence and stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
            elif not in_fence:
                m = self.header_pattern.match(line.rstrip("\n"))
                if m:
                    nodes.append(
                        StructureNode(
                            level=len(m.group("level")),
                            title=m.group("title").strip(),
                            start_offset=offset,
                        )
                    )
            offset += len(line)
        return nodes
