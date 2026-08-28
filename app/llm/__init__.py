"""
LLM 接入层（J1/J2）。

- registry: models.yaml 加载 + 角色路由 + fallback 链
- client: OpenAI 兼容统一客户端

使用范式（05 §4）：`registry.for_role("generator")` 取角色默认条目，
请求级 `model` 参数可临时覆盖（J2）。
"""

# --- 本地模块 ---
from app.llm.registry import LLMUnavailable, ModelRegistry, get_registry, registry

__all__ = ["LLMUnavailable", "ModelRegistry", "get_registry", "registry"]
