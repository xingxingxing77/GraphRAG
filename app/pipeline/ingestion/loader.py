"""
多源数据加载器（架构 P1 数据源适配器模式 · 单元 1.1）。

DataSourceAdapter 抽象基类 + LocalFileSource 实现；doc_id 采用
uuid5(source_path) 确定性生成，与 04 §2.3 doc_documents 幂等对齐。
"""

# --- 标准库 ---
import asyncio
import hashlib
import mimetypes
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

# --- 本地模块 ---
from app.core.models import RawDocument

# doc_id 命名空间（uuid5 确定性：同路径恒同 id，幂等入库）
DOC_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "graphrag://doc")

# 多编码容错链（架构 P1/FixEncoding 同链：utf-8 → utf-8-sig → gbk → latin-1）
ENCODING_CHAIN = ("utf-8", "utf-8-sig", "gbk", "latin-1")


def deterministic_doc_id(source_path: str) -> str:
    """由来源路径生成确定性 doc_id。

    Args:
        source_path: 来源路径或 URL。

    Returns:
        uuid5 字符串（同路径恒同值）。
    """
    return str(uuid.uuid5(DOC_ID_NAMESPACE, source_path))


def decode_text(raw_bytes: bytes) -> tuple[str, str]:
    """多编码容错解码。

    Args:
        raw_bytes: 原始字节。

    Returns:
        (解码文本, 实际使用编码)。

    Raises:
        UnicodeDecodeError: 编码链全部失败（latin-1 理论上不失败）。
    """
    for enc in ENCODING_CHAIN:
        try:
            return raw_bytes.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return raw_bytes.decode("latin-1"), "latin-1"


class DataSourceAdapter(ABC):
    """数据源适配器抽象基类。

    所有数据源（本地文件、Web、数据库等）均实现此接口。
    """

    @abstractmethod
    async def load(
        self, source: str, content_hash: str | None = None
    ) -> list[RawDocument]:
        """从数据源加载文档。

        Args:
            source: 数据源标识（路径、URL 等）。
            content_hash: 上游已算好的内容哈希（可选，避免重复读盘）。

        Returns:
            加载的 RawDocument 列表。
        """
        raise NotImplementedError


class LocalFileSource(DataSourceAdapter):
    """本地文件系统数据源。

    遍历指定目录或读取单个文件，产出 RawDocument。
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
        self.extensions = {e.lower() for e in (extensions or [])}
        self.max_file_size = max_file_size

    async def load(
        self, source: str, content_hash: str | None = None
    ) -> list[RawDocument]:
        """加载本地文件（单文件或目录遍历）。

        Args:
            source: 文件或目录路径。
            content_hash: 已知内容哈希（单文件时有效）。

        Returns:
            RawDocument 列表（过滤扩展名与大小后）。
        """
        root = Path(source)
        if root.is_file():
            targets = [root]
        elif root.is_dir():
            targets = sorted(p for p in root.rglob("*") if p.is_file())
        else:
            return []

        docs: list[RawDocument] = []
        for p in targets:
            if self.extensions and p.suffix.lower() not in self.extensions:
                continue
            if p.stat().st_size > self.max_file_size:
                continue
            known = content_hash if p == root else None
            doc = await self._load_one(p, known)
            docs.append(doc)
        return docs

    async def _load_one(
        self, path: Path, content_hash: str | None
    ) -> RawDocument:
        """读取单个文件为 RawDocument。

        Args:
            path: 文件路径。
            content_hash: 已知哈希（None 时现场计算）。

        Returns:
            RawDocument 契约对象。
        """
        raw_bytes = await asyncio.to_thread(path.read_bytes)
        if content_hash is None:
            content_hash = hashlib.sha256(raw_bytes).hexdigest()
        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        return RawDocument(
            doc_id=deterministic_doc_id(str(path)),
            source_path=str(path),
            raw_bytes=raw_bytes,
            mime_type=mime,
            timestamp=datetime.now(timezone.utc),
            content_hash=content_hash,
        )


class WebCrawlerSource(DataSourceAdapter):
    """网页爬取数据源——骨架（后续数据源扩展时实现）。"""

    async def load(
        self, source: str, content_hash: str | None = None
    ) -> list[RawDocument]:
        """爬取网页内容。

        Args:
            source: URL 地址。
            content_hash: 未使用。

        Returns:
            RawDocument 列表。
        """
        # TODO: 使用 httpx 爬取网页（独立超时，05 §3.3）
        raise NotImplementedError
