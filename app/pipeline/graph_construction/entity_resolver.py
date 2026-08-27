"""
G2 实体规范化与对齐（架构 P7-G2 · 单元 2.4）。

同名不同义、一义多名的处理链路：
1. 规范化：全半角/大小写统一、去修饰词（"新鲜的鲈鱼" → "鲈鱼"）；
2. 别名归并：entity_aliases.yaml 别名表（人工维护 + LLM 候选确认入库）；
3. 向量聚类消歧：实体名 embedding 相似度 ≥ 0.92 且类型相同 → 归并；
   [0.80, 0.92) 灰区 → 人工审核队列（J12 升级机制入口）。

白名单外实体统一标 Other 入开放区（zone=open），不参与固定模板检索。
"""

# --- 标准库 ---
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Literal

# --- 第三方库 ---
import yaml

# --- 本地模块 ---
from app.core.models import EntityMention, ResolvedEntity
from app.embedding.base import EmbeddingService
from app.pipeline.graph_construction.schema import GraphSchema

_DEFAULT_ALIASES_YAML = (
    Path(__file__).resolve().parents[3] / "config" / "entity_aliases.yaml"
)

# 常见修饰词前缀（规范化时剥离，架构 P7-G2 示例）
_DECORATIVE_PREFIXES: tuple[str, ...] = (
    "新鲜的", "新鲜", "冷冻的", "冷冻", "优质的", "优质",
    "上等的", "上等", "现杀的", "现摘的",
)


def normalize_name(text: str) -> str:
    """实体名规范化：全半角统一 + 小写 + 去首尾空白 + 去修饰词。

    Args:
        text: 原始实体提及。

    Returns:
        规范化后的实体名。
    """
    # NFKC：全角字母/数字/符号转半角（中文不受影响）
    normalized = unicodedata.normalize("NFKC", text).strip().lower()
    normalized = re.sub(r"\s+", "", normalized)
    for prefix in _DECORATIVE_PREFIXES:
        if normalized.startswith(prefix) and len(normalized) > len(prefix):
            normalized = normalized[len(prefix):]
            break
    return normalized


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """向量余弦相似度。

    Args:
        a: 向量 a。
        b: 向量 b。

    Returns:
        余弦相似度 [-1, 1]；零向量返回 0。
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class AliasTable:
    """实体别名表（entity_aliases.yaml）。

    Attributes:
        index: 提及（规范化后）→ (canonical_name, type) 映射，
            含 canonical 自身与全部 aliases。
    """

    def __init__(self, groups: list[dict[str, Any]]) -> None:
        """构建别名索引。

        Args:
            groups: YAML groups 段（canonical/type/aliases）。
        """
        import logging as _log

        self.index: dict[str, tuple[str, str]] = {}
        for group in groups:
            canonical = str(group.get("canonical", "")).strip()
            etype = str(group.get("type", "Other")).strip()
            if not canonical:
                continue
            key_c = normalize_name(canonical)
            if key_c in self.index:
                _log.getLogger(__name__).warning("别名冲突 canonical %r 覆盖已有 %r", canonical, self.index[key_c])
            self.index[key_c] = (canonical, etype)
            for alias in group.get("aliases") or []:
                if alias is None or str(alias).strip() == "":
                    continue
                key = normalize_name(str(alias))
                if not key:
                    continue
                if key in self.index:
                    _log.getLogger(__name__).warning("别名冲突 %r 指向 %r 覆盖已有 %r", alias, canonical, self.index[key])
                self.index[key] = (canonical, etype)

    def lookup(self, name: str) -> tuple[str, str] | None:
        """按提及查别名表。

        Args:
            name: 实体提及（内部先规范化）。

        Returns:
            (canonical_name, type)；未命中返回 None。
        """
        return self.index.get(normalize_name(name))


def load_alias_table(path: Path = _DEFAULT_ALIASES_YAML) -> AliasTable:
    """加载别名表（fail-fast，05 §6）。

    Args:
        path: entity_aliases.yaml 路径。

    Returns:
        AliasTable 实例。

    Raises:
        SystemExit: 文件缺失或结构非法。
    """
    if not path.exists():
        raise SystemExit(f"[fail-fast] 实体别名表缺失: {path}")
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    groups = raw.get("groups")
    if not isinstance(groups, list):
        raise SystemExit("[fail-fast] entity_aliases.yaml 缺少 groups 列表")
    return AliasTable(groups)


class EntityResolver:
    """实体规范化与对齐器（G2）。

    Attributes:
        schema: 图 Schema（白名单判定与对齐阈值）。
        alias_table: 别名表。
        embedding_service: 向量化服务（None 时跳过向量消歧）。
        known_canonicals: 已入库规范实体 {canonical_name: type}，
            向量消歧的比对基准。
    """

    def __init__(
        self,
        schema: GraphSchema,
        alias_table: AliasTable,
        embedding_service: EmbeddingService | None = None,
        known_canonicals: dict[str, str] | None = None,
    ) -> None:
        """初始化对齐器。

        Args:
            schema: 图 Schema。
            alias_table: 别名表。
            embedding_service: 向量化服务（可选）。
            known_canonicals: 已入库规范实体映射（可选）。
        """
        self.schema = schema
        self.alias_table = alias_table
        self.embedding_service = embedding_service
        self.known_canonicals: dict[str, str] = dict(known_canonicals or {})

    async def resolve(self, mentions: list[EntityMention]) -> list[ResolvedEntity]:
        """对实体提及批量执行规范化与对齐。

        Args:
            mentions: 实体提及列表（P5 增强层产出）。

        Returns:
            ResolvedEntity 列表（与输入等长、同序）。
        """
        results: list[ResolvedEntity] = []
        for mention in mentions:
            results.append(await self._resolve_one(mention))
        return results

    async def _resolve_one(self, mention: EntityMention) -> ResolvedEntity:
        """单个提及的对齐链路：规范化 → 别名 → 向量消歧 → 分区。

        Args:
            mention: 单个实体提及。

        Returns:
            ResolvedEntity。
        """
        norm = normalize_name(mention.name)

        # 1. 别名归并（命中即白名单 approved）
        alias_hit = self.alias_table.lookup(norm)
        if alias_hit is not None:
            canonical, etype = alias_hit
            return ResolvedEntity(
                mention=mention.name,
                canonical_name=canonical,
                type=etype,
                zone="core",
                status="approved",
            )

        # 2. 向量聚类消歧（仅当服务与基准可用）
        if self.embedding_service is not None and self.known_canonicals:
            vector_hit = await self._vector_disambiguate(norm, mention.type)
            if vector_hit is not None:
                canonical, etype, similarity, needs_review = vector_hit
                if not needs_review:
                    # ≥ 阈值且类型相同：自动归并
                    return ResolvedEntity(
                        mention=mention.name,
                        canonical_name=canonical,
                        type=etype,
                        zone="core",
                        status="approved",
                        similarity=similarity,
                    )
                # 灰区：入人工审核队列（仍按自身建开放/待审节点）
                zone: Literal["core", "open"] = (
                    "core" if self.schema.is_known_node_type(mention.type) else "open"
                )
                final_type = mention.type if zone == "core" else self.schema.open_zone.default_type
                return ResolvedEntity(
                    mention=mention.name,
                    canonical_name=norm,
                    type=final_type,
                    zone=zone,
                    status="pending",
                    similarity=similarity,
                    needs_review=True,
                )

        # 3. 白名单判定与开放区标记（J12）
        if self.schema.is_known_node_type(mention.type):
            return ResolvedEntity(
                mention=mention.name,
                canonical_name=norm,
                type=mention.type,
                zone="core",
                status="pending",
            )
        return ResolvedEntity(
            mention=mention.name,
            canonical_name=norm,
            type=self.schema.open_zone.default_type,
            zone="open",
            status="pending",
        )

    async def _vector_disambiguate(
        self, norm: str, mention_type: str
    ) -> tuple[str, str, float, bool] | None:
        """向量相似度消歧：与已入库规范实体比对。

        Args:
            norm: 规范化后的提及。
            mention_type: 提及声明的类型（类型相同才可归并）。

        Returns:
            (canonical, type, similarity, needs_review)；
            相似度低于灰区下界返回 None。
        """
        assert self.embedding_service is not None
        names = [norm, *self.known_canonicals.keys()]
        result = await self.embedding_service.embed(names)
        if len(result.dense) < 2:
            return None
        query_vec = result.dense[0]
        best_sim = -1.0
        best_name = ""
        for i, canonical in enumerate(self.known_canonicals.keys(), start=1):
            sim = cosine_similarity(query_vec, result.dense[i])
            if sim > best_sim:
                best_sim = sim
                best_name = canonical
        threshold = self.schema.alignment.vector_merge_threshold
        low = self.schema.alignment.review_low
        if best_sim < low:
            return None
        canonical_type = self.known_canonicals[best_name]
        if best_sim >= threshold and canonical_type == mention_type:
            return best_name, canonical_type, best_sim, False
        if low <= best_sim < threshold:
            return best_name, canonical_type, best_sim, True
        return None
