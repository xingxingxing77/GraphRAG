"""
认证端点（02 §3.1 · J16 · 单元 10.2）。

POST /auth/token —— 登录凭证交换签发 JWT；JWT secret 与
langgraph-server 共享（J19），agent 侧 custom auth 校验同一 token。
二选一凭证：grant_type=api_key（X-API-Key 兑换）或 password（用户密码）。
"""

# --- 标准库 ---
import time

# --- 第三方库 ---
import jwt
from fastapi import APIRouter

# --- 本地模块 ---
from app.api.errors import ApiError, ErrorCode
from app.core.config import get_settings
from app.core.models import AuthTokenRequest, TokenResponse, UserInfo

router = APIRouter()


def _issue_jwt(user_id: str, name: str, role: str, ttl: int) -> str:
    """签发 HS256 JWT（sub/name/role/exp 声明）。

    Args:
        user_id: 用户 ID（sub 声明）。
        name: 用户名。
        role: 角色（user/admin）。
        ttl: 有效期（秒）。

    Returns:
        JWT 字符串。
    """
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": user_id,
        "name": name,
        "role": role,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _authenticate_api_key(api_key: str) -> UserInfo:
    """校验 API Key（逗号分隔白名单）。

    Args:
        api_key: 提交的 API Key。

    Returns:
        UserInfo（role=admin，API Key 兑换视为管理凭证）。

    Raises:
        ApiError: AUTH_401_INVALID_API_KEY。
    """
    settings = get_settings()
    valid = {k.strip() for k in settings.valid_api_keys.split(",") if k.strip()}
    if api_key not in valid:
        raise ApiError(ErrorCode.AUTH_401_INVALID_API_KEY, "API Key 不存在或已停用")
    return UserInfo(id="api-key-user", name="api-key-user", role="admin")


def _authenticate_password(username: str, password: str) -> UserInfo:
    """校验用户密码（开发期为单一 admin 账号，生产接用户库）。

    Args:
        username: 用户名。
        password: 密码。

    Returns:
        UserInfo。

    Raises:
        ApiError: AUTH_400_BAD_CREDENTIALS。
    """
    settings = get_settings()
    if username == settings.admin_username and password == settings.admin_password:
        return UserInfo(id="u-admin", name=username, role="admin")
    raise ApiError(ErrorCode.AUTH_400_BAD_CREDENTIALS, "用户名或密码错误")


@router.post("/token", response_model=TokenResponse)
async def issue_token(request: AuthTokenRequest) -> TokenResponse:
    """签发 JWT（二选一凭证：api_key 兑换或用户密码）。

    Args:
        request: 兑换请求（grant_type=api_key | password）。

    Returns:
        TokenResponse: access_token + 有效期 + 用户信息。

    Raises:
        ApiError: AUTH_400_BAD_CREDENTIALS（密码错误）/
            AUTH_401_INVALID_API_KEY（Key 无效）/
            AUTH_400_BAD_CREDENTIALS（grant_type 与凭证不匹配）。
    """
    settings = get_settings()
    if request.grant_type == "api_key":
        if not request.api_key:
            raise ApiError(
                ErrorCode.AUTH_400_BAD_CREDENTIALS, "grant_type=api_key 需提供 api_key"
            )
        user = _authenticate_api_key(request.api_key)
    elif request.grant_type == "password":
        if not request.username or not request.password:
            raise ApiError(
                ErrorCode.AUTH_400_BAD_CREDENTIALS,
                "grant_type=password 需提供 username/password",
            )
        user = _authenticate_password(request.username, request.password)
    else:  # pragma: no cover - Literal 约束已拦截
        raise ApiError(ErrorCode.AUTH_400_BAD_CREDENTIALS, "未知 grant_type")

    token = _issue_jwt(user.id, user.name, user.role, settings.token_ttl_seconds)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.token_ttl_seconds,
        user=user,
    )
