"""
输出格式化器（架构 L8 收尾 · 单元 7.1 配套）。

对最终答案做轻量格式化：Markdown 规整 + 引用标注保留。
[n] 角标的悬浮引用卡由前端 CitationPopover 渲染（06 §6），
后端保持纯文本标注不注入 HTML（防注入，D10 同源原则）。
"""

# --- 标准库 ---
import re
from typing import Any

# 连续 3+ 换行压缩为 2（Markdown 段落规整）
_MULTI_NEWLINE = re.compile(r"\n{3,}")

# 引用角标正则
_CITATION_RE = re.compile(r"\[(\d+)\]")


class OutputFormatter:
    """输出格式化器。

    对生成的答案进行最终的格式化处理（纯文本安全，不注入 HTML）。
    """

    @staticmethod
    def format_markdown(text: str) -> str:
        """格式化为 Markdown（去行尾空白 + 压缩冗余空行）。

        Args:
            text: 原始答案文本。

        Returns:
            规整后的 Markdown 文本。
        """
        lines = [ln.rstrip() for ln in text.splitlines()]
        cleaned = "\n".join(lines).strip()
        return _MULTI_NEWLINE.sub("\n\n", cleaned)

    @staticmethod
    def add_citation_links(text: str, citations: list[dict[str, Any]]) -> str:
        """校验并保留引用角标（无效编号剔除）。

        [n] 的可点击展示由前端 CitationPopover 承担；后端仅保证
        角标编号与 citations 列表一致（无效编号剔除）。

        Args:
            text: 答案文本。
            citations: 引用信息列表（须含 marker 键）。

        Returns:
            角标校验后的答案文本。
        """
        valid_markers = {int(c.get("marker", -1)) for c in citations}

        def _sub(m: re.Match[str]) -> str:
            return m.group(0) if int(m.group(1)) in valid_markers else ""

        return _CITATION_RE.sub(_sub, text)
