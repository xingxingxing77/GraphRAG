"""
HTML 解析器（架构 P2 · 单元 1.2）。

BeautifulSoup + lxml：去标签/导航/脚本，提取正文与 h1-h6 结构树
（DOM 语义标签保留，架构 P2 表格）。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
from bs4 import BeautifulSoup, Tag

# --- 本地模块 ---
from app.core.models import ParsedDocument, RawDocument, StructureNode
from app.pipeline.ingestion.loader import decode_text

_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCK_TAGS = _HEADING_TAGS | {
    "p", "li", "td", "th", "blockquote", "pre", "figcaption", "dt", "dd",
}


class HTMLParser:
    """HTML 文档解析器。

    从 HTML 中提取正文内容，去除导航栏、脚本、样式等无关标签，
    保留 h1-h6 标题结构树与段落文本。

    Attributes:
        remove_tags: 需要移除的 HTML 标签集合。
    """

    remove_tags: set[str] = {
        "script", "style", "nav", "footer", "header",
        "aside", "iframe", "noscript",
    }

    def __init__(self, remove_tags: set[str] | None = None) -> None:
        """初始化 HTMLParser。

        Args:
            remove_tags: 自定义需要移除的标签集合，默认使用类属性。
        """
        if remove_tags is not None:
            self.remove_tags = remove_tags

    def parse(self, raw_doc: RawDocument) -> ParsedDocument:
        """解析 HTML 原始文档。

        Args:
            raw_doc: 原始文档对象，raw_bytes 应为 HTML 内容。

        Returns:
            解析后的文档对象：正文纯文本 + h1-h6 结构树 + format_meta。
        """
        html, encoding = decode_text(raw_doc.raw_bytes)
        soup = BeautifulSoup(html, "lxml")

        for tag_name in self.remove_tags:
            for t in soup.find_all(tag_name):
                t.decompose()

        root: Tag = soup.body or soup
        text, structure_tree = self._walk(root)
        meta = self._extract_meta(soup)
        return ParsedDocument(
            doc_id=raw_doc.doc_id,
            text=text.strip(),
            structure_tree=structure_tree,
            format_meta={"format": "html", "encoding": encoding, **meta},
        )

    def _walk(self, root: Tag) -> tuple[str, list[StructureNode]]:
        """深度优先遍历 DOM，拼接块级文本并记录标题偏移。

        Args:
            root: 遍历根节点。

        Returns:
            (正文纯文本, 标题结构树)。
        """
        parts: list[str] = []
        nodes: list[StructureNode] = []
        seen: set[int] = set()

        def visit(tag: Tag) -> None:
            for child in tag.children:
                if isinstance(child, Tag):
                    if child.name in _HEADING_TAGS:
                        title = child.get_text(" ", strip=True)
                        if title:
                            offset = sum(len(p) for p in parts)
                            nodes.append(
                                StructureNode(
                                    level=int(child.name[1]),
                                    title=title,
                                    start_offset=offset,
                                )
                            )
                        parts.append(title + "\n")
                        seen.add(id(child))
                    elif child.name in _BLOCK_TAGS:
                        txt = child.get_text(" ", strip=True)
                        if txt:
                            parts.append(txt + "\n")
                        seen.add(id(child))
                    if id(child) not in seen:
                        visit(child)

        visit(root)
        # 兜底：无块级结构时直接取全文
        text = "".join(parts)
        if not text.strip():
            text = root.get_text("\n", strip=True)
        return text, nodes

    def _extract_meta(self, soup: BeautifulSoup) -> dict[str, Any]:
        """提取 title / meta description。

        Args:
            soup: 解析后的 DOM。

        Returns:
            元信息字典。
        """
        meta: dict[str, Any] = {}
        if soup.title and soup.title.string:
            meta["title"] = soup.title.string.strip()
        desc = soup.find("meta", attrs={"name": "description"})
        if isinstance(desc, Tag) and desc.get("content"):
            meta["description"] = str(desc["content"])
        return meta
