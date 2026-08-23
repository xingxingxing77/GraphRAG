"""
采集编排器（架构 P1 · 单元 1.1）。

串联 scan → load → dedup → manifest 回写，产出 ScanRecord
（02 §3.11 扫描结果口径）与本批 RawDocument（P2 解析层输入）。
"""

# --- 标准库 ---
import uuid
from datetime import datetime, timezone
from pathlib import Path

# --- 本地模块 ---
from app.core.models import RawDocument, ScanRecord
from app.pipeline.config import IngestionConfig
from app.pipeline.ingestion.dedup import ContentDeduplicator
from app.pipeline.ingestion.loader import LocalFileSource
from app.pipeline.ingestion.manifest import ManifestStore
from app.pipeline.ingestion.scanner import FileScanner


class IngestionService:
    """P1 采集层编排器。"""

    def __init__(
        self,
        manifest: ManifestStore,
        config: IngestionConfig,
        base_dir: str | Path = ".",
    ) -> None:
        """初始化编排器。

        Args:
            manifest: 已处理清单存储（04 §2.3）。
            config: 采集配置（pipeline_config.yaml ingestion 段）。
            base_dir: 相对 source 路径的基准目录（通常为仓库根）。
        """
        self.manifest = manifest
        self.config = config
        self.base_dir = Path(base_dir)
        self.scanner = FileScanner(manifest)
        self.dedup = ContentDeduplicator()
        self._scan_log: list[ScanRecord] = []
        self.last_documents: list[RawDocument] = []

    async def run(self, mode: str | None = None) -> ScanRecord:
        """执行一次采集（全量/增量）。

        流程：各 source 扫描 → 变更文件加载 → 内容哈希去重
        （批内 + 跨批经 manifest）→ 清单回写 → 记录扫描结果。

        Args:
            mode: 覆盖配置默认模式（full | incremental）。

        Returns:
            ScanRecord: 本次扫描统计（02 §3.11 口径）。
        """
        run_mode = mode or self.config.mode
        discovered = 0
        deduped = 0
        kept: list[RawDocument] = []

        # 跨批去重基线：manifest 已知哈希预载
        for h in await self.manifest.known_hashes():
            self.dedup.is_duplicate(h)

        for src in self.config.sources:
            src_path = self._resolve(src.path)
            loader = LocalFileSource(
                extensions=src.extensions, max_file_size=src.max_file_size
            )
            outcome = await self.scanner.scan(
                src_path,
                mode=run_mode,
                extensions=src.extensions,
                max_file_size=src.max_file_size,
            )
            discovered += outcome.discovered
            for path in outcome.changed_paths:
                docs = await loader.load(path, outcome.hashes.get(path))
                for doc in docs:
                    if self.dedup.is_duplicate(doc.content_hash):
                        deduped += 1
                        continue
                    if not await self.manifest.put(doc):
                        deduped += 1
                        continue
                    kept.append(doc)

        record = ScanRecord(
            scan_id=f"scan-{uuid.uuid4().hex[:12]}",
            mode=run_mode,  # type: ignore[arg-type]
            discovered=discovered,
            changed=len(kept) + deduped,
            deduped=deduped,
            finished_at=datetime.now(timezone.utc),
        )
        self._scan_log.append(record)
        self.last_documents = kept
        return record

    def scan_log(self) -> list[ScanRecord]:
        """历史扫描记录（新→旧）。"""
        return list(reversed(self._scan_log))

    def _resolve(self, path: str) -> str:
        """相对路径按基准目录解析。

        Args:
            path: source 路径（可相对）。

        Returns:
            绝对路径字符串。
        """
        p = Path(path)
        return str(p if p.is_absolute() else self.base_dir / p)
