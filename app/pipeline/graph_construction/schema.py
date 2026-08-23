"""
G1 图 Schema 加载与校验（架构 P7-G1 · J12 混合式 · 单元 2.4）。

config/graph_schema.yaml 经 pydantic 校验加载（fail-fast，05 §6）：
- 核心域白名单：node_types / edge_types（质量可控，Cypher 模板固定）
- 开放区规则：type=Other，不参与固定模板检索（open_zone 段）
- 实体对齐阈值：alignment 段（vector_merge_threshold / manual_review_band）
"""

# --- 标准库 ---
from pathlib import Path

# --- 第三方库 ---
import yaml
from pydantic import BaseModel, ConfigDict, Field

_DEFAULT_SCHEMA_YAML = Path(__file__).resolve().parents[3] / "config" / "graph_schema.yaml"


class NodeTypeSpec(BaseModel):
    """白名单节点类型定义。

    Attributes:
        description: 类型说明。
        key: 主键属性（canonical_name 或 uuid）。
        properties: 允许的属性列表。
    """

    description: str = ""
    key: str = "canonical_name"
    properties: list[str] = Field(default_factory=list)


class EdgeTypeSpec(BaseModel):
    """白名单关系类型定义。

    Attributes:
        type: 关系类型名（如 REQUIRES）。
        from_type: 头节点类型（YAML 键名为 from）。
        to_type: 尾节点类型（YAML 键名为 to）。
        properties: 允许的关系属性。
    """

    model_config = ConfigDict(populate_by_name=True)

    type: str
    from_type: str = Field(alias="from")
    to_type: str = Field(alias="to")
    properties: list[str] = Field(default_factory=list)


class AlignmentConfig(BaseModel):
    """实体对齐阈值（P7-G2）。

    Attributes:
        vector_merge_threshold: ≥ 阈值且类型相同 → 自动归并。
        manual_review_band: 灰区 [low, high) → 人工审核队列。
    """

    vector_merge_threshold: float = 0.92
    manual_review_band: list[float] = Field(default_factory=lambda: [0.80, 0.92])

    @property
    def review_low(self) -> float:
        """灰区下界（含）。"""
        return self.manual_review_band[0]

    @property
    def review_high(self) -> float:
        """灰区上界（不含）。"""
        return self.manual_review_band[1]


class OpenZoneConfig(BaseModel):
    """开放区规则（J12）。

    Attributes:
        default_type: 白名单外实体的类型标记。
        participates_in_template_search: 是否参与固定模板检索（恒 False）。
        review_queue_enabled: 人工审核队列开关。
    """

    model_config = ConfigDict(extra="ignore")

    default_type: str = "Other"
    participates_in_template_search: bool = False
    review_queue: dict[str, object] = Field(default_factory=dict)

    @property
    def review_queue_enabled(self) -> bool:
        """审核队列开关。"""
        return bool(self.review_queue.get("enabled", True))


class GraphSchema(BaseModel):
    """图 Schema 顶层结构（graph_schema.yaml）。

    Attributes:
        version: 配置版本。
        node_types: 白名单节点类型表。
        edge_types: 白名单关系类型表。
        alignment: 实体对齐阈值。
        open_zone: 开放区规则。
    """

    model_config = ConfigDict(extra="ignore")

    version: int = 1
    node_types: dict[str, NodeTypeSpec] = Field(default_factory=dict)
    edge_types: list[EdgeTypeSpec] = Field(default_factory=list)
    alignment: AlignmentConfig = Field(default_factory=AlignmentConfig)
    open_zone: OpenZoneConfig = Field(default_factory=OpenZoneConfig)

    def is_known_node_type(self, type_name: str) -> bool:
        """判断实体类型是否在白名单内。

        Args:
            type_name: 实体类型名。

        Returns:
            True 表示白名单类型。
        """
        return type_name in self.node_types

    def is_allowed_edge(self, from_type: str, rel_type: str, to_type: str) -> bool:
        """校验三元组 (from)-[rel]->(to) 是否为白名单合法关系。

        Args:
            from_type: 头实体类型。
            rel_type: 关系类型。
            to_type: 尾实体类型。

        Returns:
            True 表示白名单合法关系。
        """
        return any(
            e.type == rel_type and e.from_type == from_type and e.to_type == to_type
            for e in self.edge_types
        )


def load_graph_schema(path: Path = _DEFAULT_SCHEMA_YAML) -> GraphSchema:
    """加载并校验图 Schema（fail-fast，05 §6）。

    Args:
        path: graph_schema.yaml 路径。

    Returns:
        GraphSchema: 校验通过的 Schema。

    Raises:
        SystemExit: 文件缺失或校验失败。
    """
    if not path.exists():
        raise SystemExit(f"[fail-fast] 图 Schema 配置缺失: {path}")
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    try:
        return GraphSchema.model_validate(raw)
    except Exception as exc:
        raise SystemExit(f"[fail-fast] graph_schema.yaml 校验失败: {exc}") from exc
