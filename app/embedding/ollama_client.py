"""
Ollama API 客户端封装。

封装对 Ollama 服务的 HTTP API 调用。
"""

# --- 标准库 ---
from typing import Any, Optional

# --- 第三方库 ---
import httpx


class OllamaClient:
    """Ollama REST API 客户端封装。

    提供对 Ollama 服务的 embed、chat 等 API 调用。

    Attributes:
        base_url: Ollama 服务地址。
    """

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        """初始化 Ollama 客户端。

        Args:
            base_url: Ollama 服务地址。
        """
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        """创建异步 HTTP 客户端。"""
        # TODO: 初始化 httpx.AsyncClient
        raise NotImplementedError

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        # TODO: 关闭 client
        raise NotImplementedError

    async def embed(
        self,
        model: str,
        texts: list[str],
    ) -> list[list[float]]:
        """调用 Ollama Embedding API。

        Args:
            model: 模型名称（如 bge-m3）。
            texts: 输入文本列表。

        Returns:
            向量列表。

        Raises:
            httpx.HTTPError: API 调用失败。
        """
        # TODO: POST /api/embed 请求
        raise NotImplementedError

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        stream: bool = False,
    ) -> dict[str, Any]:
        """调用 Ollama Chat API。

        Args:
            model: 模型名称。
            messages: 消息列表。
            stream: 是否流式返回。

        Returns:
            API 响应字典。
        """
        # TODO: POST /api/chat 请求
        raise NotImplementedError

    async def check_health(self) -> bool:
        """检查 Ollama 服务健康状态。

        Returns:
            True 表示服务可用。
        """
        # TODO: GET /api/tags 验证服务可达
        raise NotImplementedError
