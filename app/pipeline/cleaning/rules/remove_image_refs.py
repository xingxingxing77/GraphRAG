"""
去除 Markdown 图片引用规则。

匹配并移除 ``![alt](url)`` 格式的图片引用，
减少无关内容对检索质量的干扰。
"""

# --- 标准库 ---
import re
from dataclasses import replace
from typing import Any

# --- 本地模块 ---
from app.pipeline.base import ParsedDocument
from app.pipeline.cleaning.rules.base_rule import CleaningRule


# 匹配 Markdown 图片引用：![任意 alt](任意 url)
_IMAGE_REF_PATTERN: re.Pattern[str] = re.compile(
    r"!\[.*?\]\(.*?\)"
)


class RemoveImageRefsRule(CleaningRule):
    """去除 Markdown 图片引用规则。

    扫描文档文本，移除所有 ``![alt](url)`` 格式的图片引用标记，
    保留其他 Markdown 语法（如超链接）不受影响。

    Attributes:
        name: 规则名称 "RemoveImageRefs"。
        priority: 优先级 1（最先执行）。
    """

    name: str = "RemoveImageRefs"
    priority: int = 1

    async def process(
        self,
        doc: ParsedDocument,
        config: dict[str, Any],
    ) -> ParsedDocument:
        """移除文档文本中的 Markdown 图片引用。

        Args:
            doc: 待处理的解析后文档。
            config: 运行时配置参数，支持 key:
                - ``pattern``: 自定义正则表达式（覆盖默认模式）。

        Returns:
            文本中图片引用被移除后的文档。
        """
        # TODO: 1. 从 config 中获取自定义 pattern（如有）
        # TODO: 2. 使用 re.sub(r'!\[.*?\]\(.*?\)', '', text) 替换
        # TODO: 3. 清理替换后产生的多余空行
        # TODO: 4. 返回更新后的 ParsedDocument
        raise NotImplementedError
