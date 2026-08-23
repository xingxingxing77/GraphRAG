"""
引用标注与溯源。

在生成的答案中标注证据来源，支持可溯源。
"""

# --- 标准库 ---
from dataclasses import dataclass
from typing import Any


@dataclass
class Citation:
    """引用信息。

    Attributes:
        index: 引用序号。
        source: 文档来源路径。
        title: 文档标题。
        chunk_content: 引用的文档块内容。
        relevance_score: 相关性分数。
    """

    index: int
    source: str
    title: str
    chunk_content: str
    relevance_score: float


class CitationTracker:
    """引用追踪器。

    管理生成过程中的引用标注，将证据索引映射到答案中的标注。
    """

    def __init__(self) -> None:
        """初始化引用追踪器。"""
        self._citations: list[Citation] = []

    def add_citation(self, evidence: dict[str, Any]) -> int:
        """添加一条引用并返回引用序号。

        Args:
            evidence: 证据信息字典。

        Returns:
            引用序号（从 1 开始）。
        """
        # TODO: 创建 Citation 对象并追加到列表
        raise NotImplementedError

    def get_citations(self) -> list[Citation]:
        """获取所有引用列表。

        Returns:
            Citation 对象列表。
        """
        return self._citations.copy()

    def format_citations_text(self) -> str:
        """将引用格式化为文本。

        Returns:
            格式化的引用文本，如 "[1] 清蒸鲈鱼 (score: 0.95)"。
        """
        # TODO: 格式化引用列表为可读文本
        raise NotImplementedError

    def reset(self) -> None:
        """重置引用追踪器。"""
        self._citations.clear()
