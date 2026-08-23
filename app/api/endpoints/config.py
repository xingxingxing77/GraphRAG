"""
公共配置端点（02 §3.7）。

GET /config/public —— 可选模型条目清单 + 延迟档位枚举 + 压缩策略枚举，
J2「请求参数指定模型」的前端前提。条目清单来自 models.yaml 注册表
（api_key_ref/base_url 等敏感字段严禁下发）。
"""

# --- 第三方库 ---
from fastapi import APIRouter

# --- 本地模块 ---
from app.core.models import PublicConfig

router = APIRouter()


@router.get("/public", response_model=PublicConfig)
async def get_public_config() -> PublicConfig:
    """下发公共配置（模型条目/档位/压缩策略/Profile）。

    Returns:
        PublicConfig: 前端下拉框与档位选择所需枚举。
    """
    # TODO: JWT 鉴权依赖注入
    # TODO: 从注册表生成 ModelOption 清单（仅 id/label/provider，不含密钥引用）
    raise NotImplementedError
