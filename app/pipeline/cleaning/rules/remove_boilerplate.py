"""
去除样板文本规则（架构 P3 · 单元 1.3）。

移除版权声明、PR 请求等样板文字；patterns 配置驱动
（cleaning_rules.yaml priority 2）。
"""

# --- 标准库 ---
import re
from typing import Any

# --- 本地模块 ---
from app.core.models import CleanedDocument
from app.pipeline.cleaning.rules.base_rule import CleaningRule

# 默认样板文本匹配模式列表
_DEFAULT_PATTERNS: list[str] = [
    r"(?m)^Copyright\s.*$",
    r"(?m)^版权所有.*$",
    r"(?m)^免责声明[:：].*$",
    r"(?m)^Disclaimer[:：].*$",
    r"(?m)^点击.*?(关注|订阅|收藏).*$",
]


class RemoveBoilerplateRule(CleaningRule):
    """去除样板文本规则（配置驱动 patterns）。

    Attributes:
        name: 规则名称 "RemoveBoilerplate"。
        priority: 优先级 2。
    """

    name: str = "RemoveBoilerplate"
    priority: int = 2

    async def process(
        self,
        doc: CleanedDocument,
        config: dict[str, Any],
    ) -> CleanedDocument:
        """移除文档文本中的样板内容。

        Args:
            doc: 待处理文档。
            config: 支持 key ``patterns``（YAML 登记的样板串列表，
                按字面量或正则匹配）。

        Returns:
            样板文本被移除后的文档。
        """
        text = doc.text
        patterns: list[str] = list(config.get("patterns") or [])
        merged = [re.compile(p) for p in _DEFAULT_PATTERNS]
        for p in patterns:
            try:
                merged.append(re.compile(re.escape(p) if not _looks_like_regex(p) else p))
            except re.error:
                merged.append(re.compile(re.escape(p)))
        for pat in merged:
            text = pat.sub("", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return doc.model_copy(update={"text": text})


def _looks_like_regex(pattern: str) -> bool:
    """粗判字符串是否含正则元字符。

    Args:
        pattern: 待判断字符串。

    Returns:
        True 表示疑似正则表达式。
    """
    return any(ch in pattern for ch in r".*+?[](){}|^$\\")
