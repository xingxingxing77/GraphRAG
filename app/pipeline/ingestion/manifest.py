"""
已处理清单（Manifest）存储（架构 P1 · 04 §2.3）。

「已处理清单」= 文件路径 + 内容哈希，是增量扫描与去重判断的依据。
SSOT 为 Postgres `doc_documents` 表（04 §2.3）；开发与单测环境使用
JsonFileManifestStore（零外部依赖），二者经 ManifestStore 协议互换。
"""

# --- 标准库 ---
import json
from pathlib import Path
from typing import Protocol, runtime_checkable

# --- 本地模块 ---
from app.core.models import RawDocument


@runtime_checkable
class ManifestStore(Protocol):
    """已处理清单存储协议。

    幂等语义（04 §2.3）：put 采用「存在即跳过」（等价
    INSERT ... ON CONFLICT (content_hash) DO NOTHING），
    返回 False 表示内容已入库（重复）。
    """

    async def get_hash(self, source_path: str) -> str | None:
        """查询某来源路径已登记的内容哈希（未登记返回 None）。"""
        ...

    async def put(self, doc: RawDocument) -> bool:
        """登记一条已处理记录；内容哈希已存在时返回 False（重复跳过）。"""
        ...

    async def known_hashes(self) -> set[str]:
        """全部已登记内容哈希集合（内容级去重用）。"""
        ...


class JsonFileManifestStore:
    """JSON 文件清单（开发/测试默认，无外部依赖）。

    结构：{source_path: {doc_id, content_hash}}。
    """

    def __init__(self, manifest_path: str | Path) -> None:
        """初始化清单存储。

        Args:
            manifest_path: 清单 JSON 文件路径。
        """
        self.manifest_path = Path(manifest_path)
        self._entries: dict[str, dict[str, str]] = {}
        self._loaded = False

    def _load(self) -> None:
        """惰性加载清单文件。"""
        if self._loaded:
            return
        if self.manifest_path.exists():
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            self._entries = {str(k): dict(v) for k, v in raw.items()}
        self._loaded = True

    def _save(self) -> None:
        """持久化清单文件。"""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(self._entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    async def get_hash(self, source_path: str) -> str | None:
        """查询某来源路径已登记的内容哈希。"""
        self._load()
        entry = self._entries.get(source_path)
        return entry["content_hash"] if entry else None

    async def put(self, doc: RawDocument) -> bool:
        """登记记录；content_hash 已存在（任意路径）即判定重复。"""
        self._load()
        if doc.content_hash in await self.known_hashes():
            return False
        self._entries[doc.source_path] = {
            "doc_id": doc.doc_id,
            "content_hash": doc.content_hash,
        }
        self._save()
        return True

    async def known_hashes(self) -> set[str]:
        """全部已登记内容哈希。"""
        self._load()
        return {e["content_hash"] for e in self._entries.values()}


class PostgresManifestStore:
    """Postgres doc_documents 清单（生产 SSOT，04 §2.3）——骨架。

    列：doc_id(uuid PK) · source_path · content_hash(char64 UNIQUE) ·
    mime_type · status(管道水位) · quality_score · ingested_at/updated_at。
    写入：INSERT ... ON CONFLICT (content_hash) DO NOTHING，
    受影响行数 = 0 即判定重复跳过（04 §2.3）。
    """

    def __init__(self, dsn: str) -> None:
        """初始化 Postgres 清单存储。

        Args:
            dsn: POSTGRES_DSN 连接串。
        """
        self.dsn = dsn
        # TODO(阶段 2/3): psycopg AsyncConnection 连接池（05 §3.3 独立超时）

    async def get_hash(self, source_path: str) -> str | None:
        """按 source_path 查询 content_hash。"""
        # TODO: SELECT content_hash FROM doc_documents WHERE source_path = $1
        raise NotImplementedError

    async def put(self, doc: RawDocument) -> bool:
        """INSERT ... ON CONFLICT (content_hash) DO NOTHING 幂等写入。"""
        # TODO: 事务内写入，rowcount == 0 判定重复
        raise NotImplementedError

    async def known_hashes(self) -> set[str]:
        """全量 content_hash（大表场景改为批量布隆/分页比对）。"""
        # TODO: SELECT content_hash FROM doc_documents
        raise NotImplementedError
