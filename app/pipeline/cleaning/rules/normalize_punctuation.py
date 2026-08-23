"""
统一标点规则（架构 P3 · 单元 1.3）。

unicodedata.normalize 规范化（target_form 配置驱动，默认 NFC；
cleaning_rules.yaml priority 5）。中文语料保留全角标点，
不做全角→半角转换（可选开关 to_halfwidth）。
"""

# --- 标准库 ---
import unicodedata
from typing import Any, Literal

# --- 本地模块 ---
from app.core.models import CleanedDocument
from app.pipeline.cleaning.rules.base_rule import CleaningRule

# 常见全角标点 → 半角映射（仅 to_halfwidth=True 时启用）
_FULLWIDTH_TO_HALFWIDTH: dict[str, str] = {
    "\uff0c": ",",   # ，→ ,
    "\u3002": ".",   # 。→ .
    "\uff1a": ":",   # ：→ :
    "\uff1b": ";",   # ；→ ;
    "\uff01": "!",   # ！→ !
    "\uff1f": "?",   # ？→ ?
    "\uff08": "(",   # （→ (
    "\uff09": ")",   # ）→ )
}


class NormalizePunctuationRule(CleaningRule):
    """统一标点规则。

    Attributes:
        name: 规则名称 "NormalizePunctuation"。
        priority: 优先级 5。
    """

    name: str = "NormalizePunctuation"
    priority: int = 5

    async def process(
        self,
        doc: CleanedDocument,
        config: dict[str, Any],
    ) -> CleanedDocument:
        """统一文档中的标点符号。

        Args:
            doc: 待处理文档。
            config: 支持 key：
                - ``target_form``: 规范化形式（NFC/NFKC/NFD/NFKD，默认 NFC）。
                - ``to_halfwidth``: 是否全角转半角（默认 False）。

        Returns:
            标点被规范化后的文档。
        """
        form: Literal["NFC", "NFKC", "NFD", "NFKD"] = "NFC"
        raw_form = config.get("target_form")
        if raw_form in {"NFC", "NFKC", "NFD", "NFKD"}:
            form = raw_form
        text = unicodedata.normalize(form, doc.text)
        if bool(config.get("to_halfwidth", False)):
            for full, half in _FULLWIDTH_TO_HALFWIDTH.items():
                text = text.replace(full, half)
        return doc.model_copy(update={"text": text})
