"""
OpenAI 兼容统一 LLM 客户端（J1）。

所有云端/本地模型条目均经 OpenAI 兼容协议访问（含 Ollama /v1）。
TokenUsage 上报采用 Ollama 口径（prompt_eval_count / eval_count
自动映射，05 §4）。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
from pydantic import BaseModel, Field

# --- 本地模块 ---
from app.core.models import TokenUsage


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
        # TODO: 创建 httpx.AsyncClient / OpenAI 兼容 SDK 实例（连接池复用）

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
        response_format: dict[str, str] | None = None,
    ) -> ChatCompletion:
        """执行一次 chat 调用。

        Args:
            messages: 对话消息列表 [{"role": ..., "content": ...}]。
            temperature: 温度覆盖（缺省用条目 params 默认值）。
            model: J2 请求级模型覆盖（缺省用条目 model）。
            response_format: 结构化输出约束（如 {"type": "json_object"}，M2）。

        Returns:
            ChatCompletion: 生成结果（含 TokenUsage）。
        """
        # TODO: 组装请求（base_url/model/params 合并覆盖）
        # TODO: 独立超时（reliability.yaml，async 铁律 3）
        # TODO: Token 用量映射为 TokenUsage（Ollama 口径）
        raise NotImplementedError
