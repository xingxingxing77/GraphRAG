"""
修复编码异常规则（架构 P3 · 单元 1.3）。

移除 U+FFFD 替换字符与不可见控制字符；对 Mojibake 尝试按
encoding_chain（utf-8 → utf-8-sig → gbk → latin-1）回译修复
（cleaning_rules.yaml priority 4）。
"""

# --- 标准库 ---
import re
import unicodedata
from typing import Any

# --- 本地模块 ---
from app.core.models import CleanedDocument
from app.pipeline.cleaning.rules.base_rule import CleaningRule

# Unicode 替换字符
_REPLACEMENT_CHAR: str = "\ufffd"

# 控制字符范围（保留换行 \n、回车 \r、制表 \t）
_CONTROL_CHAR_PATTERN: re.Pattern[str] = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]"
)

# 默认编码回译链（与采集层一致）
_DEFAULT_ENCODING_CHAIN: tuple[str, ...] = ("utf-8", "utf-8-sig", "gbk", "latin-1")

# Mojibake 高频特征字符（latin-1 误解码产物）
_MOJIBAKE_MARKERS = ("Ã", "â€", "æ", "ç", "è", "é")


class FixEncodingRule(CleaningRule):
    """修复编码异常规则。

    Attributes:
        name: 规则名称 "FixEncoding"。
        priority: 优先级 4。
    """

    name: str = "FixEncoding"
    priority: int = 4

    async def process(
        self,
        doc: CleanedDocument,
        config: dict[str, Any],
    ) -> CleanedDocument:
        """修复文档中的编码异常字符。

        Args:
            doc: 待处理文档。
            config: 支持 key ``encoding_chain``（回译编码链列表）。

        Returns:
            编码异常被修复后的文档。
        """
        text = doc.text.replace(_REPLACEMENT_CHAR, "")
        text = _CONTROL_CHAR_PATTERN.sub("", text)
        text = self._try_repair_mojibake(
            text, tuple(config.get("encoding_chain") or _DEFAULT_ENCODING_CHAIN)
        )
        text = unicodedata.normalize("NFC", text)
        return doc.model_copy(update={"text": text})

    @staticmethod
    def _try_repair_mojibake(text: str, chain: tuple[str, ...]) -> str:
        """尝试将 Mojibake 文本回译为正确编码。

        仅当文本含典型乱码特征时才尝试；回译失败保持原文。

        Args:
            text: 待修复文本。
            chain: 编码回译链。

        Returns:
            修复后的文本（不可修复时返回原文）。
        """
        if not any(marker in text for marker in _MOJIBAKE_MARKERS):
            return text
        try:
            raw = text.encode("latin-1")
        except UnicodeEncodeError:
            return text
        for enc in chain:
            try:
                repaired = raw.decode(enc)
                # 修复后不再含乱码特征才采纳
                if not any(marker in repaired for marker in _MOJIBAKE_MARKERS):
                    return repaired
            except (UnicodeDecodeError, LookupError):
                continue
        return text
