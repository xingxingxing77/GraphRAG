"""
去除 Markdown 图片引用规则（架构 P3 · 单元 1.3）。

移除 ``![alt](url)`` 图片引用（配置 cleaning_rules.yaml priority 1）。
"""

# --- 标准库 ---
import re
from typing import Any

# --- 本地模块 ---
from app.core.models import CleanedDocument
from app.pipeline.cleaning.rules.base_rule import CleaningRule

# 匹配 Markdown 图片引用：![任意 alt](任意 url)
_IMAGE_REF_PATTERN: re.Pattern[str] = re.compile(r"!\[.*?\]\(.*?\)")


class RemoveImageRefsRule(CleaningRule):
    """去除 Markdown 图片引用规则。

    Attributes:
        name: 规则名称 "RemoveImageRefs"。
        priority: 优先级 1（最先执行）。
    """

    name: str = "RemoveImageRefs"
    priority: int = 1

    async def process(
        self,
        doc: CleanedDocument,
        config: dict[str, Any],
    ) -> CleanedDocument:
        """移除文档文本中的 Markdown 图片引用。

        Args:
            doc: 待处理文档。
            config: 支持 key ``pattern``（自定义正则，覆盖默认）。

        Returns:
            图片引用被移除后的文档。
        """
        pattern = _IMAGE_REF_PATTERN
        custom = config.get("pattern")
        if custom:
            pattern = re.compile(str(custom))
        text = pattern.sub("", doc.text)
        # 清理替换后残留的空白行
        text = re.sub(r"[ \t]+\n", "\n", text)
        return doc.model_copy(update={"text": text})
