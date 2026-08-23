"""
递归字符切分器（兜底策略）。

当标题级切分产生的块仍然过大时，使用递归字符切分
作为二级兜底，按多种分隔符逐步细化。
"""

# --- 标准库 ---
from typing import Any

# --- 本地模块 ---
from app.pipeline.base import Chunk


# 默认分隔符列表（从粗粒度到细粒度）
_DEFAULT_SEPARATORS: list[str] = [
    "\n\n",   # 段落分隔
    "\n",     # 行分隔
    "。",     # 中文句号
    "！",     # 中文感叹号
    "？",     # 中文问号
    ". ",     # 英文句号
    "! ",     # 英文感叹号
    "? ",     # 英文问号
    "，",     # 中文逗号
    ", ",     # 英文逗号
    " ",      # 空格
    "",       # 字符级（最终兜底）
]


class RecursiveCharacterSplitter:
    """递归字符切分器。

    使用多级分隔符列表递归切分文本。当某一级分隔符无法
    将文本切分到目标大小时，自动退化为下一级分隔符。

    Attributes:
        chunk_size: 目标 chunk 最大字符数。
        chunk_overlap: 相邻 chunk 之间的重叠字符数。
        separators: 分隔符列表（从粗到细排列）。
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        separators: list[str] | None = None,
    ) -> None:
        """初始化 RecursiveCharacterSplitter。

        Args:
            chunk_size: 目标 chunk 最大字符数，默认 500。
            chunk_overlap: chunk 重叠字符数，默认 50。
            separators: 自定义分隔符列表，默认使用 _DEFAULT_SEPARATORS。
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or list(_DEFAULT_SEPARATORS)

    def split(
        self,
        text: str,
        chunk_size: int,
        chunk_overlap: int,
        separators: list[str],
    ) -> list[Chunk]:
        """递归切分文本为文档块。

        切分策略：
        1. 使用 separators[0] 切分文本。
        2. 如果某段超过 chunk_size，使用 separators[1:] 递归切分。
        3. 合并相邻小段，确保每段尽量接近 chunk_size。
        4. 应用 chunk_overlap 在相邻块之间添加重叠。

        Args:
            text: 待切分的文本字符串。
            chunk_size: 目标最大字符数。
            chunk_overlap: 重叠字符数。
            separators: 分隔符列表（从粗到细）。

        Returns:
            切分后的 Chunk 列表。
        """
        # TODO: 1. 取 separators[0] 作为当前分隔符
        # TODO: 2. text.split(sep) 得到子段
        # TODO: 3. 合并小子段至接近 chunk_size
        # TODO: 4. 超长段使用 separators[1:] 递归
        # TODO: 5. 应用 chunk_overlap
        # TODO: 6. 构建 Chunk 对象列表并返回
        raise NotImplementedError
