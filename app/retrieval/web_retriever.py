"""
Web 搜索检索器（架构 L3 · J4 双轨 · 单元 3.4）。

J4 双轨：Tavily 主 / DuckDuckGo 兜底——无 Tavily Key 或调用失败时
自动降级 DDG。独立超时 3s 快速失败取消该路（不阻塞其余 gather 路）。
实现 BaseRetriever 协议：source=web，XML 注入围栏在生成层（05 §5.4 D10），
检索层仅标记 source=web。
"""

# --- 标准库 ---
import asyncio
import logging
from typing import Any, Callable, Optional

# --- 本地模块 ---
from app.core.models import RetrievalResult, SourceKind
from app.retrieval.base import BaseRetriever
from app.retrieval.dense_retriever import stable_hash

logger = logging.getLogger(__name__)

# 独立超时（reliability.yaml timeouts_seconds.web_search，快速失败）
_WEB_TIMEOUT_S = 3.0


class WebRetriever(BaseRetriever):
    """Web 搜索检索器（Tavily 主 / DDG 兜底）。

    Attributes:
        name: 检索来源（SourceKind.WEB）。
        error_count: 失败计数器。
    """

    name: SourceKind = SourceKind.WEB

    def __init__(
        self,
        tavily_api_key: Optional[str] = None,
        timeout_s: float = _WEB_TIMEOUT_S,
        search_fn: Optional[Callable[[str, int], list[dict[str, Any]]]] = None,
    ) -> None:
        """初始化 Web 检索器。

        Args:
            tavily_api_key: Tavily API Key（None 时走 DDG 兜底）。
            timeout_s: 独立超时（秒）。
            search_fn: 注入的搜索函数（测试替身），签名
                (query, top_k) -> [{title, content, url}, ...]。
        """
        self.tavily_api_key = tavily_api_key
        self.timeout_s = timeout_s
        self._search_fn = search_fn
        self.error_count = 0

    async def retrieve(
        self,
        query: str,
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        """执行 Web 搜索（超时/失败降级空列表）。

        Args:
            query: 搜索查询。
            top_k: 返回数量。
            filters: 预留过滤条件。

        Returns:
            检索结果列表（source="web"），失败返回空列表。
        """
        try:
            return await asyncio.wait_for(
                self._retrieve(query, top_k), timeout=self.timeout_s
            )
        except Exception as exc:  # noqa: BLE001 - 含超时，快速失败
            self.error_count += 1
            logger.warning("web 检索失败（降级空列表）: %s", exc)
            return []

    async def _retrieve(self, query: str, top_k: int) -> list[RetrievalResult]:
        """实际搜索逻辑（Tavily 主 → DDG 兜底）。

        Args:
            query: 搜索查询。
            top_k: 返回数量。

        Returns:
            检索结果列表。
        """
        if self._search_fn is not None:
            raw = await asyncio.to_thread(self._search_fn, query, top_k)
        elif self.tavily_api_key:
            raw = await asyncio.to_thread(self._search_tavily, query, top_k)
        else:
            raw = await asyncio.to_thread(self._search_ddg, query, top_k)

        results: list[RetrievalResult] = []
        for i, item in enumerate(raw[:top_k]):
            url = str(item.get("url") or "")
            content = str(item.get("content") or item.get("title") or "")
            if not content:
                continue
            results.append(
                RetrievalResult(
                    result_id=f"{self.name.value}:{stable_hash(url or str(i), content[:32])}",
                    chunk_id=None,
                    content=content,
                    score=float(item.get("score") or (1.0 - i * 0.05)),
                    source=self.name,
                    doc_id=None,
                    metadata={"url": url, "title": str(item.get("title") or "")},
                )
            )
        return results

    def _search_tavily(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """Tavily 主轨搜索（同步，供 to_thread 包裹）。

        Args:
            query: 搜索查询。
            top_k: 返回数量。

        Returns:
            [{title, content, url, score}, ...]。

        Raises:
            Exception: Tavily 调用失败（由调用方兜底 DDG 或降级）。
        """
        from tavily import TavilyClient  # 延迟导入

        client = TavilyClient(api_key=self.tavily_api_key)
        resp = client.search(query=query, max_results=top_k)
        return [
            {
                "title": r.get("title", ""),
                "content": r.get("content", ""),
                "url": r.get("url", ""),
                "score": r.get("score", 0.0),
            }
            for r in resp.get("results", [])
        ]

    def _search_ddg(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """DuckDuckGo 兜底搜索（同步，供 to_thread 包裹）。

        Args:
            query: 搜索查询。
            top_k: 返回数量。

        Returns:
            [{title, content, url}, ...]。

        Raises:
            Exception: DDG 调用失败（由调用方降级空列表）。
        """
        from ddgs import DDGS  # 延迟导入

        results: list[dict[str, Any]] = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=top_k):
                results.append(
                    {
                        "title": r.get("title", ""),
                        "content": r.get("body", ""),
                        "url": r.get("href", ""),
                    }
                )
        return results
