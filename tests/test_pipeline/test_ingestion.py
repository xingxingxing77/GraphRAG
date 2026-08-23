"""P1 采集层测试（单元 1.1 S3，07 §5 断言）。

核心断言：增量模式只处理变更文件；同内容二次入库被哈希去重拦截；
编码容错；过滤规则；真实语料（menu/HowToCook）全量采集跑通。
"""

# --- 标准库 ---
from pathlib import Path

# --- 第三方库 ---
import pytest

# --- 本地模块 ---
from app.pipeline.config import IngestionConfig, IngestionSourceConfig
from app.pipeline.ingestion.loader import (
    LocalFileSource,
    decode_text,
    deterministic_doc_id,
)
from app.pipeline.ingestion.manifest import JsonFileManifestStore
from app.pipeline.ingestion.scanner import FileScanner
from app.pipeline.ingestion.service import IngestionService

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_service(tmp_path: Path, source_dir: Path) -> IngestionService:
    """构造指向临时目录的采集编排器。"""
    manifest = JsonFileManifestStore(tmp_path / "manifest.json")
    config = IngestionConfig(
        mode="incremental",
        sources=[IngestionSourceConfig(path=str(source_dir), extensions=[".md"])],
    )
    return IngestionService(manifest=manifest, config=config, base_dir=tmp_path)


class TestIncrementalScan:
    """增量模式只处理变更文件（07 §5）。"""

    @pytest.mark.asyncio
    async def test_first_run_processes_all_files(self, tmp_path: Path) -> None:
        src = tmp_path / "docs"
        src.mkdir()
        (src / "a.md").write_text("# 清蒸鲈鱼", encoding="utf-8")
        (src / "b.md").write_text("# 红烧肉", encoding="utf-8")
        service = _make_service(tmp_path, src)

        record = await service.run(mode="incremental")
        assert record.discovered == 2
        assert len(service.last_documents) == 2

    @pytest.mark.asyncio
    async def test_second_run_without_change_processes_nothing(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "docs"
        src.mkdir()
        (src / "a.md").write_text("# 清蒸鲈鱼", encoding="utf-8")
        service = _make_service(tmp_path, src)

        await service.run(mode="incremental")
        record = await service.run(mode="incremental")
        assert record.discovered == 1
        assert len(service.last_documents) == 0
        assert record.deduped == 0  # 未变更文件在扫描层即被过滤

    @pytest.mark.asyncio
    async def test_modified_file_is_reprocessed(self, tmp_path: Path) -> None:
        src = tmp_path / "docs"
        src.mkdir()
        f = src / "a.md"
        f.write_text("# 清蒸鲈鱼 v1", encoding="utf-8")
        service = _make_service(tmp_path, src)

        await service.run(mode="incremental")
        f.write_text("# 清蒸鲈鱼 v2（修订蒸制时间）", encoding="utf-8")
        record = await service.run(mode="incremental")
        assert len(service.last_documents) == 1
        assert record.changed == 1


class TestContentDedup:
    """同内容二次入库被哈希去重拦截（07 §5）。"""

    @pytest.mark.asyncio
    async def test_full_rerun_with_same_content_is_deduped(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "docs"
        src.mkdir()
        (src / "a.md").write_text("# 同一内容", encoding="utf-8")
        service = _make_service(tmp_path, src)

        first = await service.run(mode="full")
        assert len(service.last_documents) == 1

        second = await service.run(mode="full")
        assert len(service.last_documents) == 0
        assert second.deduped == 1
        assert first.scan_id != second.scan_id

    @pytest.mark.asyncio
    async def test_duplicate_content_across_paths(self, tmp_path: Path) -> None:
        src = tmp_path / "docs"
        src.mkdir()
        content = "# 完全相同的两份内容"
        (src / "a.md").write_text(content, encoding="utf-8")
        (src / "b.md").write_text(content, encoding="utf-8")
        service = _make_service(tmp_path, src)

        record = await service.run(mode="full")
        assert len(service.last_documents) == 1
        assert record.deduped == 1


class TestFiltersAndEncoding:
    """过滤规则与编码容错。"""

    @pytest.mark.asyncio
    async def test_extension_and_size_filters(self, tmp_path: Path) -> None:
        src = tmp_path / "docs"
        src.mkdir()
        (src / "ok.md").write_text("# 正常", encoding="utf-8")
        (src / "skip.txt").write_text("非白名单扩展名", encoding="utf-8")
        big = src / "big.md"
        big.write_bytes(b"x" * 2048)
        config_ext = IngestionSourceConfig(
            path=str(src), extensions=[".md"], max_file_size=1024
        )
        manifest = JsonFileManifestStore(tmp_path / "manifest.json")
        service = IngestionService(
            manifest=manifest,
            config=IngestionConfig(sources=[config_ext]),
            base_dir=tmp_path,
        )
        record = await service.run(mode="full")
        assert record.discovered == 1  # 仅 ok.md 通过过滤

    def test_gbk_decoding_tolerant(self) -> None:
        raw = "清蒸鲈鱼：大火蒸 8 分钟".encode("gbk")
        text, enc = decode_text(raw)
        assert "清蒸鲈鱼" in text
        assert enc in {"gbk", "utf-8", "utf-8-sig", "latin-1"}

    @pytest.mark.asyncio
    async def test_gbk_file_loads_without_error(self, tmp_path: Path) -> None:
        f = tmp_path / "gbk.md"
        f.write_bytes("# 宫保鸡丁\n腌制 15 分钟".encode("gbk"))
        loader = LocalFileSource(extensions=[".md"])
        docs = await loader.load(str(f))
        assert len(docs) == 1
        text, _ = decode_text(docs[0].raw_bytes)
        assert "宫保鸡丁" in text

    def test_doc_id_deterministic(self) -> None:
        assert deterministic_doc_id("menu/a.md") == deterministic_doc_id("menu/a.md")
        assert deterministic_doc_id("menu/a.md") != deterministic_doc_id("menu/b.md")


class TestScannerContract:
    """扫描器参数校验。"""

    @pytest.mark.asyncio
    async def test_invalid_mode_raises(self, tmp_path: Path) -> None:
        manifest = JsonFileManifestStore(tmp_path / "m.json")
        scanner = FileScanner(manifest)
        with pytest.raises(ValueError):
            await scanner.scan(str(tmp_path), mode="bogus")

    @pytest.mark.asyncio
    async def test_missing_directory_raises(self, tmp_path: Path) -> None:
        manifest = JsonFileManifestStore(tmp_path / "m.json")
        scanner = FileScanner(manifest)
        with pytest.raises(ValueError):
            await scanner.scan(str(tmp_path / "not_exist"), mode="full")


class TestHowToCookCorpus:
    """真实语料端到端（准出：全量/增量各一次成功且结果列表正确）。"""

    @pytest.mark.asyncio
    async def test_full_then_incremental_on_corpus(self, tmp_path: Path) -> None:
        corpus = REPO_ROOT / "menu" / "HowToCook"
        assert corpus.is_dir(), "HowToCook 语料缺失"
        manifest = JsonFileManifestStore(tmp_path / "manifest.json")
        config = IngestionConfig(
            sources=[IngestionSourceConfig(path=str(corpus), extensions=[".md"])]
        )
        service = IngestionService(
            manifest=manifest, config=config, base_dir=REPO_ROOT
        )

        full = await service.run(mode="full")
        assert full.discovered > 100  # HowToCook 菜谱 + tips 规模
        assert len(service.last_documents) == full.discovered

        incr = await service.run(mode="incremental")
        assert incr.discovered == full.discovered
        assert len(service.last_documents) == 0  # 无变更，增量零处理

        assert len(service.scan_log()) == 2
        assert service.scan_log()[0].scan_id == incr.scan_id  # 新→旧排序
