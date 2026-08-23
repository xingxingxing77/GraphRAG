"""
递归字符切分器（架构 P4 第二级字符级兜底 · 单元 2.1）。

多级分隔符（段落 → 行 → 句号 → 分号 → 空格 → 字符）递归切分，
合并小段至接近 chunk_size，相邻块保留 chunk_overlap 重叠。
切分结果以原文偏移区间 (start, end) 表示，保证 position 精确。
"""

# --- 标准库 ---
import re

# 默认分隔符列表（chunking_config.yaml second_level.separators，从粗到细）
_DEFAULT_SEPARATORS: list[str] = ["\n\n", "\n", "。", "；", " ", ""]


class RecursiveCharacterSplitter:
    """递归字符切分器。

    Attributes:
        chunk_size: 目标 chunk 最大字符数（H3：字符计量）。
        chunk_overlap: 相邻 chunk 重叠字符数。
        separators: 分隔符列表（从粗到细，末位 "" 为字符级兜底）。
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 80,
        separators: list[str] | None = None,
    ) -> None:
        """初始化切分器。

        Args:
            chunk_size: 目标最大字符数，默认 500。
            chunk_overlap: 重叠字符数，默认 80。
            separators: 自定义分隔符列表，缺省 _DEFAULT_SEPARATORS。
        """
        self.chunk_size = max(1, chunk_size)
        # 重叠不得超过块容量的一半，防止死循环
        self.chunk_overlap = max(0, min(chunk_overlap, self.chunk_size // 2))
        self.separators = list(separators) if separators is not None else list(_DEFAULT_SEPARATORS)

    def split_spans(self, text: str) -> list[tuple[int, int]]:
        """切分文本为偏移区间列表。

        Args:
            text: 待切分文本。

        Returns:
            [(start, end), ...] 满足 text[start:end] 即块内容；
            首个区间从 0 起，末个区间至 len(text)，相邻区间含重叠。
        """
        if not text:
            return []
        atoms = self._to_atoms(text, self.separators)
        boundaries = self._merge_atoms(atoms)
        return self._apply_overlap(boundaries, len(text))

    def split_text(self, text: str) -> list[str]:
        """切分文本为内容列表（split_spans 的便捷封装）。

        Args:
            text: 待切分文本。

        Returns:
            块内容字符串列表。
        """
        return [text[s:e] for s, e in self.split_spans(text)]

    def _to_atoms(self, text: str, seps: list[str]) -> list[str]:
        """递归将文本拆解为不超过 chunk_size 的原子片段。

        保持拼接还原性："".join(atoms) == text（偏移可精确回溯）。

        Args:
            text: 当前层待拆文本。
            seps: 剩余分隔符链。

        Returns:
            原子片段列表。
        """
        if len(text) <= self.chunk_size:
            return [text]
        if not seps:
            # 无任何分隔符可用：字符级强切
            return [
                text[i : i + self.chunk_size]
                for i in range(0, len(text), self.chunk_size)
            ]
        sep = seps[0]
        if sep == "":
            return [
                text[i : i + self.chunk_size]
                for i in range(0, len(text), self.chunk_size)
            ]
        # 保留分隔符：附加到前一片段末尾，保证拼接还原
        parts = re.split(f"({re.escape(sep)})", text)
        pieces: list[str] = []
        i = 0
        while i < len(parts):
            piece = parts[i]
            if i + 1 < len(parts):
                piece += parts[i + 1]  # 附上紧随的分隔符
                i += 2
            else:
                i += 1
            if piece:
                pieces.append(piece)
        atoms: list[str] = []
        for piece in pieces:
            if len(piece) <= self.chunk_size:
                atoms.append(piece)
            else:
                # 当前分隔符粒度不够，退化到下一级
                atoms.extend(self._to_atoms(piece, seps[1:]))
        return atoms

    def _merge_atoms(self, atoms: list[str]) -> list[int]:
        """贪心合并原子至接近 chunk_size，产出块边界。

        Args:
            atoms: 原子片段列表。

        Returns:
            边界列表 [0, e1, e2, ..., len(text)]。
        """
        boundaries = [0]
        current_len = 0
        for atom in atoms:
            if current_len > 0 and current_len + len(atom) > self.chunk_size:
                boundaries.append(boundaries[-1] + current_len)
                current_len = 0
            current_len += len(atom)
        boundaries.append(boundaries[-1] + current_len)
        return boundaries

    def _apply_overlap(
        self, boundaries: list[int], text_len: int
    ) -> list[tuple[int, int]]:
        """对块边界应用重叠：后一块起点回退 overlap 字符。

        Args:
            boundaries: 无重叠块边界。
            text_len: 文本总长。

        Returns:
            [(start, end), ...] 偏移区间。
        """
        spans: list[tuple[int, int]] = []
        for i in range(len(boundaries) - 1):
            start = boundaries[i]
            end = min(boundaries[i + 1], text_len)
            if i > 0 and self.chunk_overlap > 0:
                # 回退不超过前一块起点 +1，避免完全重复
                start = max(boundaries[i] - self.chunk_overlap, spans[-1][0] + 1)
            if start < end:
                spans.append((start, end))
        return spans
