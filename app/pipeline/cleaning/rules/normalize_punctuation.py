"""
统一标点规则。

将文档中的标点符号统一为指定风格（如全角/半角），
并使用 ``unicodedata.normalize`` 规范化 Unicode 字符。
"""

# --- 标准库 ---
import unicodedata
from typing import Any

# --- 本地模块 ---
from app.pipeline.base import ParsedDocument
from app.pipeline.cleaning.rules.base_rule import CleaningRule


# 常见全角标点 → 半角映射（可按需扩展）
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

    处理文档中的标点符号：
    - 使用 ``unicodedata.normalize`` 执行 Unicode 规范化（NFC / NFKC）。
    - 可选地将全角标点转换为半角（或反向）。
    - 统一引号风格（弯引号 → 直引号）。

    Attributes:
        name: 规则名称 "NormalizePunctuation"。
        priority: 优先级 5。
        normalization_form: Unicode 规范化形式，默认 "NFC"。
        to_halfwidth: 是否将全角标点转为半角，默认 False。
    """

    name: str = "NormalizePunctuation"
    priority: int = 5

    def __init__(
        self,
        normalization_form: str = "NFC",
        to_halfwidth: bool = False,
    ) -> None:
        """初始化 NormalizePunctuationRule。

        Args:
            normalization_form: unicodedata.normalize 的规范化形式，
                可选 "NFC"、"NFKC"、"NFD"、"NFKD"。
            to_halfwidth: 是否将全角标点转换为半角。
        """
        self.normalization_form = normalization_form
        self.to_halfwidth = to_halfwidth

    async def process(
        self,
        doc: ParsedDocument,
        config: dict[str, Any],
    ) -> ParsedDocument:
        """统一文档中的标点符号。

        处理步骤：
        1. 使用 ``unicodedata.normalize(normalization_form, text)`` 规范化。
        2. 若 ``to_halfwidth`` 为 True，替换全角标点为半角。
        3. 统一弯引号为直引号（``"..."`` → ``"..."``）。

        Args:
            doc: 待处理的解析后文档。
            config: 运行时配置参数，支持 key:
                - ``normalization_form``: 覆盖默认规范化形式。
                - ``to_halfwidth``: 覆盖默认全角转半角设置。

        Returns:
            标点被规范化后的文档。
        """
        # TODO: 1. unicodedata.normalize(self.normalization_form, text)
        # TODO: 2. 若 to_halfwidth，遍历 _FULLWIDTH_TO_HALFWIDTH 替换
        # TODO: 3. 替换弯引号 → 直引号
        # TODO: 4. 返回更新后的 ParsedDocument
        raise NotImplementedError
