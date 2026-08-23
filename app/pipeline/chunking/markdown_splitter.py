"""
Markdown 标题层级切分器（架构 P4 第一级结构分块 · 单元 2.1）。

按 ATX 标题（# ~ ####）将文档切分为带标题路径的节（HeaderSection），
维护标题栈生成 title_path；围栏代码块内的伪标题不作切分点。
"""

# --- 标准库 ---
import re
from dataclasses import dataclass, field

# 匹配 ATX 标题（行首 # ~ ######）
_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^(?P<level>#{1,6})\s+(?P<title>.+?)\s*#*\s*$"
)

# 默认切分层级（chunking_config.yaml first_level.headers_to_split_on）
_DEFAULT_HEADER_LEVELS: tuple[int, ...] = (1, 2, 3, 4)


@dataclass
class HeaderSection:
    """标题切分产出的文档节（分块中间表示）。

    Attributes:
        title_path: 标题路径（如 ["清蒸鲈鱼", "操作步骤", "蒸制"]）。
        level: 当前节所属标题层级（0 表示文档根）。
        start_offset: 节内容在原文中的起始字符偏移。
        end_offset: 节内容在原文中的结束字符偏移（不含）。
        text: 节内容文本（原文切片，含标题行）。
    """

    title_path: list[str] = field(default_factory=list)
    level: int = 0
    start_offset: int = 0
    end_offset: int = 0
    text: str = ""


class MarkdownHeaderSplitter:
    """Markdown 标题层级切分器。

    Attributes:
        header_levels: 作为切分点的标题级别集合（默认 1-4 级）。
    """

    def __init__(self, header_levels: list[int] | None = None) -> None:
        """初始化切分器。

        Args:
            header_levels: 参与切分的标题级别列表，缺省 [1,2,3,4]。
        """
        self.header_levels = set(header_levels or _DEFAULT_HEADER_LEVELS)

    def split(self, text: str) -> list[HeaderSection]:
        """按标题切分文本为节列表。

        无标题时返回单个根节（整篇文档），供字符级兜底判定。

        Args:
            text: 待切分的 Markdown 文本。

        Returns:
            HeaderSection 列表（按原文顺序，偏移精确到字符）。
        """
        headings = self._scan_headings(text)
        if not headings:
            return [
                HeaderSection(
                    title_path=[],
                    level=0,
                    start_offset=0,
                    end_offset=len(text),
                    text=text,
                )
            ]

        sections: list[HeaderSection] = []
        # 首个标题之前的前言（preamble）作为根节
        if headings[0][0] > 0:
            sections.append(
                HeaderSection(
                    title_path=[],
                    level=0,
                    start_offset=0,
                    end_offset=headings[0][0],
                    text=text[: headings[0][0]],
                )
            )

        stack: list[tuple[int, str]] = []  # (level, title) 标题栈
        for i, (offset, level, title) in enumerate(headings):
            # 弹栈至当前级别的父级，生成 title_path
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            title_path = [t for _, t in stack]

            end = headings[i + 1][0] if i + 1 < len(headings) else len(text)
            sections.append(
                HeaderSection(
                    title_path=title_path,
                    level=level,
                    start_offset=offset,
                    end_offset=end,
                    text=text[offset:end],
                )
            )
        return sections

    def _scan_headings(self, text: str) -> list[tuple[int, int, str]]:
        """扫描标题行（跳过围栏代码块内伪标题）。

        Args:
            text: Markdown 文本。

        Returns:
            [(行偏移, 级别, 标题文本), ...] 按偏移升序。
        """
        headings: list[tuple[int, int, str]] = []
        in_fence = False
        fence_marker = ""
        offset = 0
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if not in_fence and (
                stripped.startswith("```") or stripped.startswith("~~~")
            ):
                in_fence = True
                fence_marker = stripped[:3]
            elif in_fence and stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
            elif not in_fence:
                m = _HEADER_PATTERN.match(line.rstrip("\n"))
                if m:
                    level = len(m.group("level"))
                    if level in self.header_levels:
                        headings.append((offset, level, m.group("title").strip()))
            offset += len(line)
        return headings
