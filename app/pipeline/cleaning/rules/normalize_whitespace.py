"""
合并多余空白规则（架构 P3 · 单元 1.3）。

连续 4+ 换行压缩为 2 个换行（cleaning_rules.yaml priority 3 口径），
移除行尾空白，规范首尾空白。
"""

# --- 标准库 ---
import re
from typing import Any

# --- 本地模块 ---
from app.core.models import CleanedDocument
from app.pipeline.cleaning.rules.base_rule import CleaningRule

# 连续 4 个及以上换行 → 压缩为 2 个换行（YAML 登记口径）
_EXCESS_NEWLINES_PATTERN: re.Pattern[str] = re.compile(r"\n{4,}")
# 行尾多余空白
_TRAILING_WHITESPACE_PATTERN: re.Pattern[str] = re.compile(r"[ \t]+$", re.MULTILINE)


class NormalizeWhitespaceRule(CleaningRule):
    """合并多余空白规则。

    Attributes:
        name: 规则名称 "NormalizeWhitespace"。
        priority: 优先级 3。
    """

    name: str = "NormalizeWhitespace"
    priority: int = 3

    async def process(
        self,
        doc: CleanedDocument,
        config: dict[str, Any],
    ) -> CleanedDocument:
        """合并文档中的多余空白字符。

        Args:
            doc: 待处理文档。
            config: 运行时配置参数（当前未使用）。

        Returns:
            空白被规范化后的文档。
        """
        text = _EXCESS_NEWLINES_PATTERN.sub("\n\n", doc.text)
        text = _TRAILING_WHITESPACE_PATTERN.sub("", text)
        text = text.strip()
        return doc.model_copy(update={"text": text})
