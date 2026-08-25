"""
langgraph-server custom auth（J19/J16 · 单元 10.3）。

与业务面同源 JWT：解析 Bearer token（settings.jwt_secret 共享），
同时兼容 SDK 以 x-api-key 头携带 token。认证通过后资源级授权
全局放行（开发期）；thread 归属隔离经 run 入参 user_id + 会话
端点归属校验承担（02 §3.2，10.2 session_store 同源逻辑）。
"""

# --- 标准库 ---
from typing import Any

# --- 第三方库 ---
import jwt as pyjwt
from langgraph_sdk import Auth

# --- 本地模块 ---
from app.core.config import get_settings

auth = Auth()


def _extract_token(authorization: str | None, headers: dict | None) -> str | None:
    """从 Authorization Bearer 或 x-api-key 头提取 token。

    Args:
        authorization: Authorization 头值（可能为 None）。
        headers: 原始头字典（键值可能为 bytes）。

    Returns:
        token 字符串；缺失返回 None。
    """
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            return token.strip()
    if headers:
        for key in (b"x-api-key", "x-api-key"):
            raw = headers.get(key)
            if raw:
                return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    return None


@auth.authenticate
async def authenticate(
    authorization: str | None = None,
    headers: dict | None = None,
) -> dict:
    """认证处理器：校验同源 JWT，返回用户身份。

    Args:
        authorization: Authorization 头。
        headers: 请求头（兼容 x-api-key）。

    Returns:
        含 identity/role/display_name 的用户字典。

    Raises:
        Auth.exceptions.HTTPException: 401（缺失/过期/非法凭证）。
    """
    token = _extract_token(authorization, headers)
    if not token:
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="缺少凭证（Bearer 或 x-api-key）"
        )
    settings = get_settings()
    try:
        payload = pyjwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except pyjwt.ExpiredSignatureError as exc:
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="JWT 已过期"
        ) from exc
    except pyjwt.InvalidTokenError as exc:
        raise Auth.exceptions.HTTPException(
            status_code=401, detail="JWT 签名校验失败"
        ) from exc

    identity = str(payload.get("sub", "anonymous"))
    return {
        "identity": identity,
        "display_name": str(payload.get("name", identity)),
        "role": str(payload.get("role", "user")),
        "permissions": [str(payload.get("role", "user"))],
    }


@auth.on
async def allow_authenticated(
    ctx: Auth.types.AuthContext, value: Any
) -> bool:
    """全局资源授权（开发期放行所有已认证用户）。

    thread/assistant 的跨用户隔离由会话归属校验承担（10.2）；
    生产收紧时在此按 ctx.user 追加 metadata owner 过滤。

    Args:
        ctx: 授权上下文（含 user/resource/action）。
        value: 资源值。

    Returns:
        True 放行。
    """
    return True
