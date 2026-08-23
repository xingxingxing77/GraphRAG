"""
Pipeline 抽象基类与数据模型。

定义管道规则的统一接口和各层之间的中间表示。
"""

# --- 标准库 ---
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RawDocument:
    """P1 采集层输出：原始文档。

    Attributes:
        source_path: 文件来源路径。
        raw_bytes: 原始字节内容。
        mime_type: MIME 类型。
        timestamp: 采集时间戳。
        content_hash: 内容 SHA-256 哈希。
    """

    source_path: str
    raw_bytes: bytes
    mime_type: str
    timestamp: float
    content_hash: str


@dataclass
class ParsedDocument:
    """P2 解析层输出：解析后的文档。

    Attributes:
        text: 纯文本内容。
        structure_tree: 结构树（标题层级等）。
        format_meta: 格式相关元数据。
        source_path: 原始来源路径。
    """

    text: str
    structure_tree: list[dict[str, Any]] = field(default_factory=list)
    format_meta: dict[str, Any] = field(default_factory=dict)
    source_path: str = ""


@dataclass
class CleanedDocument:
    """P3 清洗层输出：清洗后的文档。

    Attributes:
        text: 清洗后的文本。
        quality_score: 质量评分 [0, 1]。
        cleaned_meta: 清洗过程元数据。
        source_path: 原始来源路径。
    """

    text: str
    quality_score: float = 1.0
    cleaned_meta: dict[str, Any] = field(default_factory=dict)
    source_path: str = ""


@dataclass
class Chunk:
    """P4 分块层输出：文档块。

    Attributes:
        content: 块内容。
        metadata: 元数据字典。
        parent_ref: 父文档引用。
        position: 在原文档中的位置序号。
        title_path: 标题路径（如 "清蒸鲈鱼 > 操作步骤 > 蒸制"）。
    """

    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_ref: str = ""
    position: int = 0
    title_path: str = ""


@dataclass
class EnrichedChunk:
    """P5 增强层输出：增强后的文档块。

    Attributes:
        content: 块内容。
        metadata: 增强后的元数据。
        embeddings_meta: 向量化相关元数据。
        relations: 关系信息。
    """

    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embeddings_meta: dict[str, Any] = field(default_factory=dict)
    relations: list[dict[str, Any]] = field(default_factory=list)


class PipelineRule(ABC):
    """管道规则抽象基类。

    所有清洗规则、分块步骤等均继承此基类，
    实现统一的插件化处理接口。

    Attributes:
        name: 规则名称。
        enabled: 是否启用。
        priority: 优先级（数字越小越先执行）。
    """

    name: str = ""
    enabled: bool = True
    priority: int = 50

    @abstractmethod
    async def process(self, doc: Any, config: dict[str, Any]) -> Any:
        """处理单个文档/块。

        Args:
            doc: 输入文档（类型取决于所在管道层）。
            config: 配置参数。

        Returns:
            处理后的文档。
        """
        raise NotImplementedError
