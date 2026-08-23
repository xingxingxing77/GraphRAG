"""
Pipeline 抽象基类。

定义管道规则的统一接口。管道各层的中间表示（RawDocument →
EnrichedChunk 五模型族）属于跨层数据契约，统一定义在
`app.core.models`（D1 契约唯一来源），本模块仅做兼容再导出。
"""

# --- 标准库 ---
from abc import ABC, abstractmethod
from typing import Any

# --- 本地模块（契约再导出，保持历史 import 路径兼容） ---
from app.core.models import (  # noqa: F401
    Chunk,
    CleanedDocument,
    EnrichedChunk,
    EntityMention,
    ParsedDocument,
    PositionMeta,
    RawDocument,
    RelationTriple,
    StructureNode,
)


class PipelineRule(ABC):
    """管道规则抽象基类。

    所有清洗规则、分块步骤等均继承此基类，
    实现统一的插件化处理接口。

    清洗规则（P3）的输入输出均为 CleanedDocument（架构 §3.1）；
    开发流程见 05 §5.6。

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
            doc: 输入文档（类型取决于所在管道层，契约模型见 app.core.models）。
            config: 配置参数。

        Returns:
            处理后的文档。
        """
        raise NotImplementedError
