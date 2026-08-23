"""
文件扫描器（架构 P1 文件发现策略 · 单元 1.1）。

全量扫描 vs 增量扫描：维护「已处理清单」（ManifestStore，04 §2.3），
增量模式以 SHA-256 内容哈希比对，只处理新增/变更部分。
过滤规则：扩展名白名单 + 文件大小上限。
"""

# --- 标准库 ---
import asyncio
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

# --- 本地模块 ---
from app.pipeline.ingestion.manifest import ManifestStore

DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB（pipeline_config.yaml ingestion）


@dataclass
class ScanOutcome:
    """一次扫描的结果。

    Attributes:
        discovered: 通过过滤规则的候选文件总数。
        changed_paths: 需要处理的文件路径（全量=全部候选；增量=新增/变更）。
        hashes: 变更文件的内容哈希（避免加载阶段重复读盘）。
    """

    discovered: int = 0
    changed_paths: list[str] = field(default_factory=list)
    hashes: dict[str, str] = field(default_factory=dict)


class FileScanner:
    """文件扫描器：目录遍历 + 过滤 + 增量哈希比对。"""

    def __init__(self, manifest: ManifestStore) -> None:
        """初始化扫描器。

        Args:
            manifest: 已处理清单存储（04 §2.3 SSOT 的可替换实现）。
        """
        self.manifest = manifest

    async def scan(
        self,
        directory: str,
        mode: str = "incremental",
        extensions: list[str] | None = None,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
    ) -> ScanOutcome:
        """扫描目录获取待处理文件列表。

        Args:
            directory: 目录路径。
            mode: 扫描模式，``full`` 全量或 ``incremental`` 增量。
            extensions: 文件扩展名白名单（如 [".md"]）。
            max_file_size: 文件大小上限（字节），超限文件跳过。

        Returns:
            ScanOutcome: 候选统计与待处理文件（含哈希）。

        Raises:
            ValueError: mode 非法或目录不存在。
        """
        if mode not in {"full", "incremental"}:
            raise ValueError(f"非法扫描模式: {mode}")
        root = Path(directory)
        if not root.is_dir():
            raise ValueError(f"目录不存在: {directory}")

        allowed = {e.lower() for e in (extensions or [])}
        candidates: list[Path] = []
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            if allowed and p.suffix.lower() not in allowed:
                continue
            if p.stat().st_size > max_file_size:
                continue
            candidates.append(p)

        outcome = ScanOutcome(discovered=len(candidates))
        if mode == "full":
            outcome.changed_paths = [str(p) for p in candidates]
            return outcome

        # 增量：SHA-256 与清单比对，仅保留新增/变更（架构 P1）
        for p in candidates:
            digest = await asyncio.to_thread(self._hash_file, p)
            recorded = await self.manifest.get_hash(str(p))
            if recorded != digest:
                outcome.changed_paths.append(str(p))
                outcome.hashes[str(p)] = digest
        return outcome

    @staticmethod
    def _hash_file(path: Path) -> str:
        """计算文件 SHA-256（分块读，避免大文件占内存）。

        Args:
            path: 文件路径。

        Returns:
            SHA-256 十六进制摘要。
        """
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
