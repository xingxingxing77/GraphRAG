"""
清洗规则抽象基类。

所有具体清洗规则均继承此基类，
实现统一的 process 接口以接入 CleaningPipeline。
"""

# --- 标准库 ---
from abc import abstractmethod
from typing import Any

# --- 本地模块 ---
from app.pipeline.base import PipelineRule, ParsedDocument


class CleaningRule(PipelineRule):
    """清洗规则抽象基类。

    继承 PipelineRule，为清洗层的所有规则提供统一接口。
    子类必须实现 process 方法。

    Attributes:
        name: 规则名称（子类覆盖）。
        enabled: 是否启用，默认 True。
        priority: 执行优先级（数字越小越先执行，子类覆盖）。
    """

    @abstractmethod
    async def process(
        self,
        doc: ParsedDocument,
        config: dict[str, Any],
    ) -> ParsedDocument:
        """对解析后文档执行单条清洗规则。

        Args:
            doc: 待处理的解析后文档。
            config: 运行时配置参数。

        Returns:
            处理后的文档（可以是修改后的同一对象或新对象）。
        """
        raise NotImplementedError
