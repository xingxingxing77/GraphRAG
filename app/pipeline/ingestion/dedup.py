"""
内容去重器。

基于内容哈希（SHA-256）避免同一内容重复入库。
"""

# --- 标准库 ---
import hashlib


class ContentDeduplicator:
    """内容去重器。

    基于 SHA-256 哈希值进行内容级去重。
    """

    def __init__(self) -> None:
        """初始化去重器。"""
        self._seen_hashes: set[str] = set()

    def compute_hash(self, content: bytes) -> str:
        """计算内容的 SHA-256 哈希。

        Args:
            content: 原始字节内容。

        Returns:
            SHA-256 哈希值。
        """
        return hashlib.sha256(content).hexdigest()

    def is_duplicate(self, content_hash: str) -> bool:
        """检查是否为重复内容。

        Args:
            content_hash: 内容哈希。

        Returns:
            True 表示重复。
        """
        if content_hash in self._seen_hashes:
            return True
        self._seen_hashes.add(content_hash)
        return False

    def filter_duplicates(
        self,
        items: list[tuple[str, bytes]],
    ) -> tuple[list[tuple[str, bytes]], int]:
        """过滤重复项（架构 P1 内容去重）。

        Args:
            items: (路径, 内容) 元组列表。

        Returns:
            (去重后的列表, 被拦截的重复数)。
        """
        kept: list[tuple[str, bytes]] = []
        deduped = 0
        for path, content in items:
            digest = self.compute_hash(content)
            if self.is_duplicate(digest):
                deduped += 1
                continue
            kept.append((path, content))
        return kept, deduped
