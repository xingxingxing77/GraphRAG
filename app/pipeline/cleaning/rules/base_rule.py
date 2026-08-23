"""
清洗规则抽象基类（架构 P3 规则链模式 · 单元 1.3）。

契约对齐（架构 §3.1）：清洗规则的输入输出均为 CleanedDocument。
"""

# --- 标准库 ---
from abc import abstractmethod
from typing import Any

# --- 本地模块 ---
from app.core.models import CleanedDocument
from app.pipeline.base import PipelineRule


class CleaningRule(PipelineRule):
    """清洗规则抽象基类。

    继承 PipelineRule，子类实现 process（CleanedDocument → CleanedDocument）。
    执行记录由 CleaningPipeline 统一写入 cleaned_meta。

    Attributes:
        name: 规则名称（子类覆盖，与 cleaning_rules.yaml 登记一致）。
        enabled: 是否启用，默认 True。
        priority: 执行优先级（数字越小越先执行，子类覆盖）。
    """

    @abstractmethod
    async def process(
        self,
        doc: CleanedDocument,
        config: dict[str, Any],
    ) -> CleanedDocument:
        """对清洗态文档执行单条规则。

        Args:
            doc: 待处理文档（CleanedDocument）。
            config: 运行时配置参数（YAML 规则参数）。

        Returns:
            处理后的 CleanedDocument。
        """
        raise NotImplementedError
