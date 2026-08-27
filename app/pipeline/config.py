"""
管道配置加载（D7 · 05 §6 fail-fast）。

config/pipeline_config.yaml 经 pydantic 校验加载，失败即拒绝启动。
本节先落地 ingestion 段（单元 1.1），其余段随关联单元扩展。
"""

# --- 标准库 ---
import os
from pathlib import Path
from typing import Literal

# --- 第三方库 ---
import yaml
from pydantic import BaseModel, Field

_DEFAULT_PIPELINE_YAML = Path(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config",
        "pipeline_config.yaml",
    )
)
_DEFAULT_CLEANING_YAML = Path(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config",
        "cleaning_rules.yaml",
    )
)


class IngestionSourceConfig(BaseModel):
    """单个采集数据源配置（pipeline_config.yaml pipeline.ingestion.sources）。

    Attributes:
        type: 数据源类型（当前仅 local_file）。
        path: 采集目录路径。
        extensions: 扩展名白名单。
        max_file_size: 文件大小上限（字节）。
    """

    type: Literal["local_file"] = "local_file"
    path: str
    extensions: list[str] = Field(default_factory=lambda: [".md"])
    max_file_size: int = 10 * 1024 * 1024


class IngestionConfig(BaseModel):
    """P1 采集层配置。

    Attributes:
        mode: 默认扫描模式。
        scan_interval: 扫描间隔（秒）。
        dedup_by: 去重依据（固定 content_hash，架构 P1）。
        sources: 数据源列表。
    """

    mode: Literal["full", "incremental"] = "incremental"
    scan_interval: int = 3600
    dedup_by: str = "content_hash"
    sources: list[IngestionSourceConfig] = Field(default_factory=list)


class PipelineSection(BaseModel):
    """pipeline 段聚合（其余子段随单元扩展，extra=ignore 兼容）。"""

    model_config = {"extra": "ignore"}

    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    chunking: "ChunkingConfig" = Field(default_factory=lambda: ChunkingConfig())


# ============================================================
# P4 分块层配置（config/pipeline_config.yaml chunking 段，单元 2.1）
# ============================================================


class FirstLevelConfig(BaseModel):
    """第一级结构分块配置（markdown_header）。"""

    model_config = {"extra": "ignore"}

    type: str = "markdown_header"
    headers_to_split_on: list[list[str]] = Field(
        default_factory=lambda: [["#", "h1"], ["##", "h2"], ["###", "h3"], ["####", "h4"]]
    )
    keep_separator: bool = True

    def header_levels(self) -> list[int]:
        """从 [["#","h1"],...] 推导切分标题级别列表。"""
        return [len(pair[0]) for pair in self.headers_to_split_on if pair]


class SecondLevelConfig(BaseModel):
    """第二级字符级兜底配置（recursive_character，H3 字符计量）。"""

    model_config = {"extra": "ignore"}

    type: str = "recursive_character"
    chunk_size: int = 500
    chunk_overlap: int = 80
    separators: list[str] = Field(
        default_factory=lambda: ["\n\n", "\n", "。", "；", " ", ""]
    )


class ChunkConstraints(BaseModel):
    """分块约束（架构 P4 关键参数）。"""

    model_config = {"extra": "ignore"}

    min_chunk_size: int = 50
    max_chunk_size: int = 1500


class ContextPreservationConfig(BaseModel):
    """上下文保留策略开关。"""

    model_config = {"extra": "ignore"}

    prefix_injection: bool = True
    parent_ref: bool = True
    summary_attachment: bool = False


class ChunkingConfig(BaseModel):
    """P4 分块层配置（hierarchical 多级策略）。"""

    model_config = {"extra": "ignore"}

    strategy: str = "hierarchical"
    first_level: FirstLevelConfig = Field(default_factory=FirstLevelConfig)
    second_level: SecondLevelConfig = Field(default_factory=SecondLevelConfig)
    constraints: ChunkConstraints = Field(default_factory=ChunkConstraints)
    context_preservation: ContextPreservationConfig = Field(
        default_factory=ContextPreservationConfig
    )


# 回填前向引用（PipelineSection.chunking）
PipelineSection.model_rebuild()


class PipelineConfig(BaseModel):
    """pipeline_config.yaml 顶层结构。"""

    model_config = {"extra": "ignore"}

    pipeline: PipelineSection = Field(default_factory=PipelineSection)


def load_pipeline_config(path: Path = _DEFAULT_PIPELINE_YAML) -> PipelineConfig:
    """加载并校验管道配置（fail-fast，05 §6）。

    Args:
        path: pipeline_config.yaml 路径。

    Returns:
        PipelineConfig: 校验通过的配置。

    Raises:
        SystemExit: 文件缺失或校验失败。
    """
    if not path.exists():
        raise SystemExit(f"[fail-fast] 管道配置缺失: {path}")
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        raise SystemExit(f"[fail-fast] 管道配置为空: {path}")
    try:
        return PipelineConfig.model_validate(raw)
    except Exception as exc:
        raise SystemExit(f"[fail-fast] pipeline_config.yaml 校验失败: {exc}") from exc


# ============================================================
# 清洗规则配置（config/cleaning_rules.yaml，单元 1.3）
# ============================================================


class CleaningRuleConfig(BaseModel):
    """单条清洗规则配置。

    Attributes:
        name: 规则名（与规则类 name 属性一致）。
        enabled: 是否启用。
        priority: 优先级（越小越先执行）。
        description: 描述（仅文档用途）。
        params: 其余参数（patterns/encoding_chain/target_form 等）透传规则。
    """

    model_config = {"extra": "allow"}

    name: str
    enabled: bool = True
    priority: int = 50
    description: str = ""

    def rule_params(self) -> dict[str, object]:
        """提取透传给规则 process 的参数（排除登记字段）。"""
        excluded = {"name", "enabled", "priority", "description"}
        extra = self.model_dump(exclude=excluded)
        return {k: v for k, v in extra.items() if v is not None}


class QualityGateConfig(BaseModel):
    """质量门控配置（cleaning_rules.yaml quality_gate 段）。"""

    model_config = {"extra": "ignore"}

    enabled: bool = True
    priority: int = 99
    min_length: int = 20
    language: str = "zh"
    dedup_method: str = "simhash"
    dedup_threshold: float = 0.9
    sensitive_patterns: list[str] = Field(default_factory=list)


class CleaningPipelineConfig(BaseModel):
    """cleaning_rules.yaml 顶层结构。"""

    model_config = {"extra": "ignore"}

    rules: list[CleaningRuleConfig] = Field(default_factory=list)
    quality_gate: QualityGateConfig = Field(default_factory=QualityGateConfig)


def load_cleaning_config(path: Path = _DEFAULT_CLEANING_YAML) -> CleaningPipelineConfig:
    """加载并校验清洗规则配置（fail-fast，05 §6）。

    Args:
        path: cleaning_rules.yaml 路径。

    Returns:
        CleaningPipelineConfig: 校验通过的配置。

    Raises:
        SystemExit: 文件缺失或校验失败。
    """
    if not path.exists():
        raise SystemExit(f"[fail-fast] 清洗规则配置缺失: {path}")
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        raise SystemExit(f"[fail-fast] cleaning_rules.yaml 为空: {path}")
    section = (raw or {}).get("cleaning_pipeline", {})
    try:
        return CleaningPipelineConfig.model_validate(section)
    except Exception as exc:
        raise SystemExit(f"[fail-fast] cleaning_rules.yaml 校验失败: {exc}") from exc
