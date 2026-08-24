"""
OpenAI 兼容统一 LLM 客户端（J1 · 单元 5.2 前置）。

所有云端/本地模型条目均经 OpenAI 兼容协议访问（含 Ollama /v1）。
TokenUsage 上报采用 Ollama 口径（prompt_eval_count / eval_count
自动映射，05 §4）。独立超时取 reliability.yaml llm_call（铁律 3）。
"""

# --- 标准库 ---
import logging
import time
from typing import Any

# --- 第三方库 ---
import httpx
from pydantic import BaseModel, Field

# --- 本地模块 ---
from app.api.metrics import record_llm_tokens
from app.core.models import TokenUsage

logger = logging.getLogger(__name__)

# 独立超时（reliability.yaml timeouts_seconds.llm_call）
_LLM_TIMEOUT_S = 30.0


class ModelEntry(BaseModel):
    """models.yaml 单个模型条目。

    Attributes:
        base_url: OpenAI 兼容端点。
        api_key_ref: 环境变量名（取值时查 os.environ，缺失 fail-fast）。
        model: 模型标识。
        params: 默认推理参数（temperature 等）。
    """

    base_url: str
    api_key_ref: str
    model: str
    params: dict[str, Any] = Field(default_factory=dict)


class ChatCompletion(BaseModel):
    """一次 chat 调用的响应载荷。

    Attributes:
        content: 生成文本。
        model: 实际使用的模型标识。
        usage: Token 用量（追加至 AgentState.token_usage）。
        raw: 供应商原始响应（调试用，生产不落日志明文）。
    """

    content: str
    model: str = ""
    usage: TokenUsage | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class LLMClient:
    """绑定单个注册表条目的 OpenAI 兼容客户端。"""

    def __init__(self, entry: ModelEntry, api_key: str) -> None:
        """初始化客户端。

        Args:
            entry: ModelEntry 注册表条目（base_url/model/params）。
            api_key: 已解析的密钥（api_key_ref → os.environ）。
        """
        self.entry = entry
        self.api_key = api_key

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
        response_format: dict[str, str] | None = None,
    ) -> ChatCompletion:
        """执行一次 chat 调用（独立超时，铁律 3）。

        Args:
            messages: 对话消息列表 [{"role": ..., "content": ...}]。
            temperature: 温度覆盖（缺省用条目 params 默认值）。
            model: J2 请求级模型覆盖（缺省用条目 model）。
            response_format: 结构化输出约束（如 {"type": "json_object"}，M2）。

        Returns:
            ChatCompletion: 生成结果（含 TokenUsage）。

        Raises:
            httpx.HTTPError: 网络/超时/非 2xx（由 fallback 链接管）。
            RuntimeError: 响应体结构异常。
        """
        payload: dict[str, Any] = {
            "model": model or self.entry.model,
            "messages": messages,
            "stream": False,
        }
        merged = dict(self.entry.params)
        if temperature is not None:
            merged["temperature"] = temperature
        payload.update(merged)
        if response_format is not None:
            payload["response_format"] = response_format

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=_LLM_TIMEOUT_S) as client:
            resp = await client.post(
                f"{self.entry.base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
        latency_ms = int((time.perf_counter() - start) * 1000)

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"LLM 响应缺少 choices: {self.entry.model}")
        content = str(choices[0].get("message", {}).get("content") or "")
        usage = self._map_usage(data, latency_ms)
        if usage is not None:
            record_llm_tokens("prompt", usage.model, usage.prompt_tokens)
            record_llm_tokens("completion", usage.model, usage.completion_tokens)
        return ChatCompletion(
            content=content,
            model=str(data.get("model") or payload["model"]),
            usage=usage,
            raw=data,
        )

    def _map_usage(self, data: dict[str, Any], latency_ms: int) -> TokenUsage | None:
        """映射 Token 用量（Ollama 口径优先，兼容 OpenAI 口径）。

        Args:
            data: 供应商原始响应体。
            latency_ms: 调用耗时（毫秒）。

        Returns:
            TokenUsage；无用量字段时返回 None。
        """
        usage_raw = data.get("usage") or {}
        if not usage_raw:
            return None
        prompt_tokens = int(
            usage_raw.get("prompt_eval_count")
            or usage_raw.get("prompt_tokens")
            or 0
        )
        completion_tokens = int(
            usage_raw.get("eval_count")
            or usage_raw.get("completion_tokens")
            or 0
        )
        return TokenUsage(
            model=self.entry.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )
