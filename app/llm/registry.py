"""
模型注册表：models.yaml 加载 + 角色路由（J2）+ fallback 链。

规则（config/models.yaml 头注 + 05 §4/§6）：
- 条目名 = 请求参数可引用的 model 标识
- api_key_ref 指向环境变量名，密钥不落 YAML 明文（D7/J16）
- 新增模型 = YAML 加条目，零代码改动
- 配置校验失败启动即暴露（fail-fast，05 §6）
"""

# --- 标准库 ---
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

# --- 第三方库 ---
import yaml
from pydantic import BaseModel, Field, model_validator

# --- 本地模块 ---
from app.llm.client import ChatCompletion, LLMClient, ModelEntry

logger = logging.getLogger(__name__)

# 默认注册表文件（基于本文件定位仓库根，不依赖运行时工作目录）— 用 abspath 避免 Path.resolve 阻塞
_DEFAULT_MODELS_YAML = Path(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config",
        "models.yaml",
    )
)


class LLMUnavailable(Exception):
    """fallback 链全部失败时抛出（05 §4）。

    generator 节点捕获后降级轻量模型并置 degraded=True
    （X-Degraded: llm-fallback）。
    """


# base_url 里的 ${VAR} 占位符：部署拓扑相关地址不写死在 YAML（宿主经
# localhost 可达的 Ollama，在 agent 容器内 localhost 指容器自身 → 连接被拒，
# 须按环境注入 host.docker.internal）。与 api_key_ref 同一注入思路（D7）。
_ENV_TOKEN = re.compile(r"\$\{(\w+)}")


def _expand_env(value: str) -> str:
    """展开字符串中的 ${VAR} 占位符。

    取值优先 os.environ（compose/容器注入），缺省回落 AppSettings 同名字段
    默认值 —— 使宿主裸跑无需任何配置即保持原行为。

    Args:
        value: 可能含 ${VAR} 的字符串。

    Returns:
        展开后的字符串（无占位符则原样返回）。

    Raises:
        SystemExit: 占位符引用的变量既不在环境中也无配置默认值（fail-fast）。
    """
    from app.core.config import get_settings

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        # m5：空串视同未设置——`OLLAMA_BASE_URL=` 之类空值若直接放行，
        # base_url 会静默变成 "/v1" 打向非法地址
        raw = os.environ.get(name) or None
        if raw is None:
            alt = getattr(get_settings(), name.lower(), None)
            if alt is None:
                raise SystemExit(
                    f"[fail-fast] models.yaml 占位符引用未配置的变量: {name}"
                )
            raw = str(alt)
        return raw

    return _ENV_TOKEN.sub(_sub, value)


class ModelsConfig(BaseModel):
    """models.yaml 整体结构（models + roles + fallback_chain）。

    Attributes:
        models: 条目注册表。
        roles: 角色 → 条目名路由（query_understanding/generator/judge/extractor）。
        fallback_chain: generator 角色失败时的按序回退条目。
    """

    models: dict[str, ModelEntry]
    roles: dict[str, str] = Field(default_factory=dict)
    fallback_chain: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_references(self) -> "ModelsConfig":
        """roles 与 fallback_chain 引用的条目必须已注册。"""
        for role, entry_name in self.roles.items():
            if entry_name not in self.models:
                raise ValueError(f"roles.{role} 引用了未注册条目: {entry_name}")
        for entry_name in self.fallback_chain:
            if entry_name not in self.models:
                raise ValueError(f"fallback_chain 引用了未注册条目: {entry_name}")
        return self


class ModelRegistry:
    """模型注册表（角色路由 + fallback 链 + 密钥解析）。"""

    def __init__(self, config: ModelsConfig) -> None:
        """初始化注册表。

        Args:
            config: 校验通过的 models.yaml 配置。
        """
        self.config = config

    @classmethod
    def from_yaml(cls, path: Path = _DEFAULT_MODELS_YAML) -> "ModelRegistry":
        """从 YAML 加载并校验注册表（失败 fail-fast，05 §6）。

        Args:
            path: models.yaml 路径。

        Returns:
            ModelRegistry: 校验通过的注册表实例。

        Raises:
            SystemExit: 文件缺失或校验失败（启动即暴露配置错误）。
        """
        if not path.exists():
            raise SystemExit(f"[fail-fast] 模型注册表缺失: {path}")
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if raw is None:
            raise SystemExit(f"[fail-fast] 模型注册表为空: {path}")
        # 地址类字段按运行环境展开（同一 YAML 需在宿主/容器两种拓扑下可用）
        for entry in (raw.get("models") or {}).values():
            if isinstance(entry, dict) and isinstance(entry.get("base_url"), str):
                entry["base_url"] = _expand_env(entry["base_url"])
        try:
            config = ModelsConfig.model_validate(raw)
        except Exception as exc:  # pydantic 校验错误聚合抛出
            raise SystemExit(f"[fail-fast] models.yaml 校验失败: {exc}") from exc
        return cls(config)

    def resolve_api_key(self, entry: ModelEntry) -> str:
        """解析条目密钥（查 os.environ，缺失 fail-fast，D7/J16）。

        Args:
            entry: 模型条目。

        Returns:
            密钥值（本地端点占位可为空串）。

        Raises:
            SystemExit: 环境变量缺失。
        """
        api_key = os.environ.get(entry.api_key_ref)
        if api_key is None:
            raise SystemExit(
                f"[fail-fast] 模型条目 api_key_ref 环境变量缺失: {entry.api_key_ref}"
            )
        return api_key

    def entry_for_role(self, role: str) -> ModelEntry:
        """角色路由：取角色默认条目。

        Args:
            role: 角色名（query_understanding/generator/judge/extractor）。

        Returns:
            ModelEntry: 角色默认条目。

        Raises:
            KeyError: 角色未配置。
        """
        entry_name = self.config.roles[role]
        return self.config.models[entry_name]

    def for_role(self, role: str) -> LLMClient:
        """为角色创建客户端（角色默认条目）。

        Args:
            role: 角色名。

        Returns:
            LLMClient: 绑定角色默认条目的客户端。
        """
        entry = self.entry_for_role(role)
        return LLMClient(entry=entry, api_key=self.resolve_api_key(entry))

    def for_model(self, model_name: str) -> LLMClient:
        """按条目名创建客户端（J2 请求级覆盖）。

        Args:
            model_name: 注册表条目名。

        Returns:
            LLMClient: 绑定指定条目的客户端。

        Raises:
            KeyError: 条目未注册。
        """
        entry = self.config.models[model_name]
        return LLMClient(entry=entry, api_key=self.resolve_api_key(entry))

    async def chat_with_fallback(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> ChatCompletion:
        """按 fallback_chain 依次重试的生成调用（05 §4）。

        Args:
            messages: 对话消息列表。
            **kwargs: 透传 LLMClient.chat 的参数。

        Returns:
            ChatCompletion: 首个成功条目的响应。

        Raises:
            LLMUnavailable: 全链失败（调用方降级并置 degraded=True，
                X-Degraded: llm-fallback）。
        """
        errors: list[str] = []
        for entry_name in self.config.fallback_chain:
            entry = self.config.models.get(entry_name)
            if entry is None:
                errors.append(f"{entry_name}: 条目未注册")
                continue
            try:
                client = LLMClient(entry=entry, api_key=self.resolve_api_key(entry))
                return await client.chat(messages, **kwargs)
            except SystemExit:
                raise  # api_key_ref 缺失为配置错误，fail-fast 不上抛为降级
            except Exception as exc:  # 条目失败记录后继续下一条目
                errors.append(f"{entry_name}: {exc}")
                logger.warning("LLM 条目 %s 调用失败，尝试下一条目: %s", entry_name, exc)
        raise LLMUnavailable(f"fallback 链全部失败: {errors}")


@lru_cache
def get_registry() -> ModelRegistry:
    """获取全局注册表单例。

    Returns:
        ModelRegistry: 从 config/models.yaml 加载的注册表。
    """
    return ModelRegistry.from_yaml()


# 05 §4 使用范式入口：registry.for_role("generator")
registry = get_registry()
