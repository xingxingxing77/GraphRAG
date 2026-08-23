"""
格式路由器。

按 MIME type / 文件扩展名将原始文档分发到对应的解析器。
"""

# --- 标准库 ---
import mimetypes
from pathlib import Path
from typing import Any

# --- 本地模块 ---
from app.pipeline.base import RawDocument, ParsedDocument


# MIME type 到解析器名称的映射（默认）
_MIME_ROUTER_MAP: dict[str, str] = {
    "text/markdown": "markdown",
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
            mime_map: 自定义 MIME type 到解析器名称的映射，默认使用 _MIME_ROUTER_MAP。
            ext_map: 自定义扩展名到解析器名称的映射，默认使用 _EXT_ROUTER_MAP。
        """
        self.mime_map: dict[str, str] = mime_map or _MIME_ROUTER_MAP
        self.ext_map: dict[str, str] = ext_map or _EXT_ROUTER_MAP

    def route(self, file_path: str) -> str:
        """根据文件路径返回对应的解析器名称。

        优先使用 MIME type 判断，无法识别时退回到扩展名判断。

        Args:
            file_path: 文件路径。

        Returns:
            解析器名称字符串，如 "markdown"、"html"、"pdf"。

        Raises:
            ValueError: 无法识别文件格式。
        """
        # TODO: 1. 通过 mimetypes.guess_type 推断 MIME type
        # TODO: 2. 在 mime_map 中查找对应解析器
        # TODO: 3. 兜底使用 ext_map 按扩展名查找
        # TODO: 4. 均无匹配时抛出 ValueError
        raise NotImplementedError

    async def parse(self, raw_doc: RawDocument) -> ParsedDocument:
        """路由并调用对应解析器处理原始文档。

        Args:
            raw_doc: 原始文档对象。

        Returns:
            解析后的文档对象。

        Raises:
            ValueError: 无法识别文档格式。
        """
        # TODO: 1. 调用 self.route 获取解析器名称
        # TODO: 2. 根据名称实例化/获取对应解析器
        # TODO: 3. 调用解析器的 parse 方法并返回结果
        raise NotImplementedError
