"""
清洗管道编排器。

按优先级（priority）排序并依次执行已启用的清洗规则，
将 ParsedDocument 转换为 CleanedDocument。
"""

# --- 标准库 ---
import logging
from typing import Any

# --- 本地模块 ---
from app.pipeline.base import ParsedDocument, CleanedDocument

logger = logging.getLogger(__name__)


class CleaningPipeline:
    """清洗管道编排器。

    管理一组清洗规则（CleaningRule），按 priority 升序依次执行，
    完成文档从解析态到清洗态的转换。

    Attributes:
        rules: 已注册的清洗规则列表（按 priority 排序）。
    """

    def __init__(self) -> None:
        """初始化清洗管道。"""
        self._rules: list[Any] = []  # CleaningRule 实例列表

    def add_rule(self, rule: Any) -> None:
        """注册一条清洗规则。

        规则注册后会立即按 priority 重新排序。

        Args:
            rule: CleaningRule 实例，必须具有 name、enabled、priority 属性。
        """
        # TODO: 1. 校验 rule 是否为 CleaningRule 子类
        # TODO: 2. 追加到 self._rules
        # TODO: 3. 按 priority 升序排序
        raise NotImplementedError

    async def run(
        self,
        doc: ParsedDocument,
        config: dict[str, Any] | None = None,
    ) -> CleanedDocument:
        """执行清洗管道。

        按 priority 顺序依次调用每条已启用规则的 process 方法，
        最终将结果转换为 CleanedDocument。

        Args:
            doc: 待清洗的解析后文档。
            config: 运行时配置参数，可覆盖规则的默认行为。

        Returns:
            清洗后的文档对象。

        Raises:
            RuntimeError: 某条规则执行失败且未配置容错时抛出。
        """
        # TODO: 1. 初始化 current_doc = doc（ParsedDocument）
        # TODO: 2. 遍历 self._rules，跳过 enabled=False 的规则
        # TODO: 3. 调用 rule.process(current_doc, config or {})
        # TODO: 4. 将最终结果转换为 CleanedDocument
        # TODO: 5. 计算并填充 quality_score
        # TODO: 6. 记录清洗过程日志
        raise NotImplementedError

    @property
    def rule_names(self) -> list[str]:
        """返回已注册规则的名称列表（按执行顺序）。

        Returns:
            规则名称字符串列表。
        """
        return [rule.name for rule in self._rules]
