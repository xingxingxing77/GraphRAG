"""
检索结果去重器（架构 L4 · 单元 3.5）。

基于 result_id（默认键）或内容哈希去重：同一文档被多路召回时
保留分数最高的一条，保持原有排序。
"""

# --- 标准库 ---
import hashlib

# --- 本地模块 ---
from app.core.models import RetrievalResult


class Deduplicator:
    """检索结果去重器。

    当同一条文档被多路检索器召回时，去除重复项，
    保留分数最高的一条记录。
    """

    @staticmethod
    def deduplicate(
        results: list[RetrievalResult],
        strategy: str = "result_id",
    ) -> list[RetrievalResult]:
        """对检索结果去重。

        Args:
            results: 待去重的结果列表。
            strategy: 去重键策略：
                ``result_id``（默认，融合层去重键）、
                ``content_hash``（内容哈希）、
                ``metadata_id``（chunk_id/doc_id 元数据）。

        Returns:
            去重后的结果列表，保持原有排序（同键保留最高分）。
        """
        best: dict[str, RetrievalResult] = {}
        order: list[str] = []
        for r in results:
            key = Deduplicator._key_for(r, strategy)
            if key not in best:
                best[key] = r
                order.append(key)
            elif r.score > best[key].score:
                best[key] = r
        return [best[k] for k in order]

    @staticmethod
    def _key_for(result: RetrievalResult, strategy: str) -> str:
        """按策略计算去重键。

        Args:
            result: 检索结果。
            strategy: 去重键策略。

        Returns:
            去重键字符串。
        """
        if strategy == "content_hash":
            return Deduplicator._content_hash(result.content)
        if strategy == "metadata_id":
            return result.chunk_id or result.doc_id or result.result_id
        return result.result_id

    @staticmethod
    def _content_hash(content: str) -> str:
        """计算内容的 SHA-256 哈希。

        Args:
            content: 文档内容。

        Returns:
            SHA-256 哈希值。
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def merge_same_document(
        results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        """合并同一文档的多个 chunk（按 doc_id 分组，内容拼接）。

        Args:
            results: 检索结果列表。

        Returns:
            合并后的结果列表（每 doc_id 一条，保持首次出现顺序）。
        """
        merged: dict[str, RetrievalResult] = {}
        order: list[str] = []
        for r in results:
            key = r.doc_id or r.result_id
            if key not in merged:
                merged[key] = r
                order.append(key)
            else:
                current = merged[key]
                merged[key] = current.model_copy(
                    update={
                        "content": f"{current.content}\n{r.content}",
                        "score": max(current.score, r.score),
                    }
                )
        return [merged[k] for k in order]
