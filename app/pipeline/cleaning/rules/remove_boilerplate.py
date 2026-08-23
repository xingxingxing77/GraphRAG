"""
去除样板文本规则。

移除文档中常见的样板/模板文本，如版权声明、免责声明、
导航提示、广告文案等，提升文档内容纯度。
"""

# --- 标准库 ---
import re
from typing import Any

# --- 本地模块 ---
from app.pipeline.base import ParsedDocument
from app.pipeline.cleaning.rules.base_rule import CleaningRule


# 默认样板文本匹配模式列表
_DEFAULT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?m)^Copyright\s.*$", re.IGNORECASE),
    re.compile(r"(?m)^版权所有.*$"),
    re.compile(r"(?m)^免责声明[:：].*$"),
    re.compile(r"(?m)^Disclaimer[:：].*$", re.IGNORECASE),
    re.compile(r"(?m)^点击.*?(关注|订阅|收藏).*$"),
]


class RemoveBoilerplateRule(CleaningRule):
    """去除样板文本规则。

    使用可配置的正则表达式列表，匹配并移除文档中常见的样板文本。
    patterns 可通过构造函数或 config 参数传入，未指定时使用默认列表。

    Attributes:
        name: 规则名称 "RemoveBoilerplate"。
        priority: 优先级 2。
        patterns: 样板文本匹配模式列表。
    """

    name: str = "RemoveBoilerplate"
    priority: int = 2

    def __init__(
        self,
        patterns: list[re.Pattern[str]] | None = None,
    ) -> None:
        """初始化 RemoveBoilerplateRule。

        Args:
            patterns: 自定义样板文本正则表达式列表，默认使用 _DEFAULT_PATTERNS。
        """
        self.patterns: list[re.Pattern[str]] = patterns or list(_DEFAULT_PATTERNS)

    async def process(
        self,
        doc: ParsedDocument,
        config: dict[str, Any],
    ) -> ParsedDocument:
        """移除文档文本中的样板内容。

        依次用 patterns 中的每个正则表达式执行替换。
        config 中可传入 ``extra_patterns``（字符串列表）追加匹配模式。

        Args:
            doc: 待处理的解析后文档。
            config: 运行时配置参数，支持 key:
                - ``extra_patterns``: 额外的正则表达式字符串列表。

        Returns:
            样板文本被移除后的文档。
        """
        # TODO: 1. 合并 self.patterns + config 中的 extra_patterns
        # TODO: 2. 依次对 doc.text 执行 re.sub 替换
        # TODO: 3. 清理多余空行
        # TODO: 4. 返回更新后的 ParsedDocument
        raise NotImplementedError
