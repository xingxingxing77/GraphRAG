"""
多源数据加载器。

使用适配器模式从各种数据源获取原始内容。
"""

# --- 标准库 ---
from abc import ABC, abstractmethod
from pathlib import Path

# --- 本地模块 ---
from app.pipeline.base import RawDocument


class DataSourceAdapter(ABC):
    """数据源适配器抽象基类。

    所有数据源（本地文件、Web、数据库等）均实现此接口。
    """

    @abstractmethod
    async def load(self, source: str) -> list[RawDocument]:
        """从数据源加载文档。

        Args:
            source: 数据源标识（路径、URL 等）。

        Returns:
            加载的 RawDocument 列表。
        """
        raise NotImplementedError


class LocalFileSource(DataSourceAdapter):
    """本地文件系统数据源。

    遍历指定目录，加载匹配的文件。
    """

    def __init__(
        self,
        extensions: list[str] | None = None,
        max_file_size: int = 10 * 1024 * 1024,
    ) -> None:
        """初始化本地文件数据源。

        Args:
            extensions: 允许的文件扩展名白名单。
            max_file_size: 最大文件大小（字节）。
        """
        self.extensions = extensions or [".md", ".txt", ".html", ".pdf"]
        self.max_file_size = max_file_size

    async def load(self, source: str) -> list[RawDocument]:
        """加载本地文件。

        Args:
            source: 目录路径。

        Returns:
            RawDocument 列表。
        """
        # TODO: 遍历目录，过滤扩展名和大小
        # TODO: 读取文件内容，计算 content_hash
        # TODO: 支持多编码容错读取（utf-8 -> utf-8-sig -> gbk -> latin-1）
        raise NotImplementedError


class WebCrawlerSource(DataSourceAdapter):
    """网页爬取数据源。"""

    async def load(self, source: str) -> list[RawDocument]:
        """爬取网页内容。

        Args:
            source: URL 地址。

        Returns:
            RawDocument 列表。
        """
        # TODO: 使用 httpx 爬取网页
        raise NotImplementedError
