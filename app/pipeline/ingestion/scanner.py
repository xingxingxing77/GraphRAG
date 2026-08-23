"""
文件扫描器。

支持全量扫描和增量扫描（基于文件修改时间/哈希）。
"""

# --- 标准库 ---
from pathlib import Path
from typing import Optional


class FileScanner:
    """文件扫描器。

    维护「已处理清单」，支持增量加载，只处理变更部分。
    """

    def __init__(self, manifest_path: str = ".scan_manifest.json") -> None:
        """初始化扫描器。

        Args:
            manifest_path: 已处理清单文件路径。
        """
        self.manifest_path = manifest_path
        self._manifest: dict[str, str] = {}  # {file_path: content_hash}

    async def scan(
        self,
        directory: str,
        mode: str = "incremental",
        extensions: list[str] | None = None,
    ) -> list[str]:
        """扫描目录获取文件列表。

        Args:
            directory: 目录路径。
            mode: 扫描模式，``full`` 全量或 ``incremental`` 增量。
            extensions: 文件扩展名白名单。

        Returns:
            需要处理的文件路径列表。
        """
        # TODO: 加载 manifest
        # TODO: 遍历目录收集文件
        # TODO: 如果是增量模式，过滤已处理的文件
        raise NotImplementedError

    async def update_manifest(
        self,
        file_path: str,
        content_hash: str,
    ) -> None:
        """更新已处理清单。

        Args:
            file_path: 文件路径。
            content_hash: 内容哈希。
        """
        # TODO: 更新并持久化 manifest
        raise NotImplementedError
