"""
Ollama API 客户端封装（架构 §6.2 · 单元 2.3）。

封装对 Ollama 服务 HTTP API 的异步调用（embed/chat/健康检查），
每个外部调用携带独立超时（05 §3.3 async 铁律 3）。
"""

# --- 标准库 ---
from typing import Any, Optional

# --- 第三方库 ---
import httpx

# 默认独立超时（reliability.yaml timeouts_seconds.llm_call / embedding）
_DEFAULT_TIMEOUT = 30.0


class OllamaClient:
    """Ollama REST API 客户端封装。

    Attributes:
        base_url: Ollama 服务地址。
        timeout: 请求独立超时（秒）。
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        """初始化 Ollama 客户端。

        Args:
            base_url: Ollama 服务地址。
            timeout: 请求独立超时（秒）。
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        """创建异步 HTTP 客户端（连接池复用）。"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout
            )

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """确保客户端已连接。

        Returns:
            httpx.AsyncClient 实例。
        """
        if self._client is None:
            await self.connect()
        assert self._client is not None
        return self._client

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        """调用 Ollama Embedding API（POST /api/embed，批量输入）。

        Args:
            model: 模型名称（如 bge-m3）。
            texts: 输入文本列表。

        Returns:
            向量列表，shape (n, dim)。

        Raises:
            httpx.HTTPError: API 调用失败。
        """
        client = await self._ensure_client()
        resp = await client.post(
            "/api/embed", json={"model": model, "input": texts}
        )
        resp.raise_for_status()
        payload = resp.json()
        embeddings: list[list[float]] = payload.get("embeddings", [])
        return [[float(x) for x in vec] for vec in embeddings]

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        stream: bool = False,
    ) -> dict[str, Any]:
        """调用 Ollama Chat API（POST /api/chat）。

        Args:
            model: 模型名称。
            messages: 消息列表。
            stream: 是否流式返回（骨架仅支持非流式）。

        Returns:
            API 响应字典（含 message / prompt_eval_count / eval_count）。

        Raises:
            httpx.HTTPError: API 调用失败。
        """
        client = await self._ensure_client()
        resp = await client.post(
            "/api/chat",
            json={"model": model, "messages": messages, "stream": stream},
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    async def check_health(self) -> bool:
        """检查 Ollama 服务健康状态（GET /api/tags）。

        Returns:
            True 表示服务可达。
        """
        try:
            client = await self._ensure_client()
            resp = await client.get("/api/tags")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
