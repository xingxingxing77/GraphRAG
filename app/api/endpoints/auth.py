"""
认证端点（02 §3.1，J16）。

POST /auth/token —— 登录凭证交换签发 JWT；JWT secret 与
langgraph-server 共享（J19），agent 侧 custom auth 校验同一 token。
"""

# --- 第三方库 ---
from fastapi import APIRouter

# --- 本地模块 ---
from app.core.models import AuthTokenRequest, TokenResponse

router = APIRouter()


@router.post("/token", response_model=TokenResponse)
async def issue_token(request: AuthTokenRequest) -> TokenResponse:
    """签发 JWT（二选一凭证：api_key 兑换或用户密码）。

    Args:
        request: 兑换请求（grant_type=api_key | password）。

    Returns:
        TokenResponse: access_token + 有效期 + 用户信息。

    Raises:
        HTTPException: AUTH_400_BAD_CREDENTIALS（凭证错误）/
            AUTH_401_INVALID_API_KEY / AUTH_429_RATE_LIMITED（兑换限流更严）。
    """
    # TODO: grant_type=api_key 校验 X-API-Key 有效性
    # TODO: grant_type=password 校验用户凭证
    # TODO: PyJWT 签发（JWT_SECRET 环境变量，与 langgraph-server 共享）
    # TODO: 兑换限流（Redis 计数器）
    raise NotImplementedError
