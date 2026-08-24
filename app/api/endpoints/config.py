"""
公共配置端点（02 §3.7 · 单元 10.2）。

GET /config/public —— 可选模型条目清单 + 延迟档位枚举 + 压缩策略枚举，
J2「请求参数指定模型」的前端前提。条目清单来自 models.yaml 注册表
（api_key_ref/base_url 等敏感字段严禁下发）。
"""

# --- 第三方库 ---
from fastapi import APIRouter

# --- 本地模块 ---
from app.core.models import ModelOption, PublicConfig

router = APIRouter()

# 本地端点识别特征（provider 判定）
_LOCAL_MARKERS = ("localhost", "127.0.0.1", "host.docker.internal")


def _provider_of(base_url: str) -> str:
    """按 base_url 判定提供方（cloud/local）。

    Args:
        base_url: 模型条目端点。

    Returns:
        "local" 或 "cloud"。
    """
    return "local" if any(m in base_url for m in _LOCAL_MARKERS) else "cloud"


@router.get("/public", response_model=PublicConfig)
async def get_public_config() -> PublicConfig:
    """下发公共配置（模型条目/档位/压缩策略/Profile）。

    敏感字段（api_key_ref/base_url）严禁下发；Profile 由 generator
    角色条目提供方判定（cloud-primary / local）。

    Returns:
        PublicConfig: 前端下拉框与档位选择所需枚举。
    """
    from app.llm.registry import get_registry

    registry = get_registry()
    models = [
        ModelOption(
            id=name,
            label=entry.model,
            provider=_provider_of(entry.base_url),  # type: ignore[arg-type]
        )
        for name, entry in registry.config.models.items()
    ]

    # Profile：generator 角色条目提供方判定
    try:
        generator_entry = registry.entry_for_role("generator")
        profile = (
            "local" if _provider_of(generator_entry.base_url) == "local"
            else "cloud-primary"
        )
    except KeyError:
        profile = "cloud-primary"

    return PublicConfig(models=models, profile=profile)
