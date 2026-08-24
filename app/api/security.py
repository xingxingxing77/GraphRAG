"""
安全加固模块（架构 §7.3 D10 · 单元 9.3）。

- 日志脱敏钩子：手机号/身份证/邮箱正则掩码（05 §3.4）；
- JWT 校验：PyJWT 解码 Bearer token（secret 与 langgraph-server
  共享，J16/J19）；
- RBAC 依赖：require_admin 非 admin 返回 403 AUTH_403_FORBIDDEN。
"""

# --- 标准库 ---
import logging
import re
from typing import Any

# --- 第三方库 ---
import jwt
from fastapi import Depends, Request

# --- 本地模块 ---
from app.api.errors import ApiError, ErrorCode
from app.core.config import get_settings

# --- PII 正则（05 §3.4 脱敏钩子） ---
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def mask_pii(text: str) -> str:
    """脱敏钩子：手机号/身份证/邮箱掩码。

    Args:
        text: 原始文本（query/answer/日志字段）。

    Returns:
        脱敏后的文本。
    """
    text = _ID_CARD_RE.sub("***IDCARD***", text)
    text = _PHONE_RE.sub("***PHONE***", text)
    text = _EMAIL_RE.sub("***EMAIL***", text)
    return text


class MaskingFilter(logging.Filter):
    """日志脱敏过滤器（挂到 handler，05 §3.4）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        """对日志消息执行脱敏（就地修改）。

        Args:
            record: 日志记录。

        Returns:
            恒 True（仅改写不拦截）。
        """
        if isinstance(record.msg, str):
            record.msg = mask_pii(record.msg)
        if record.args:
            args = record.args if isinstance(record.args, tuple) else (record.args,)
            record.args = tuple(
                mask_pii(a) if isinstance(a, str) else a for a in args
            )
        return True


def decode_bearer_token(token: str) -> dict[str, Any]:
    """解码 JWT（HS256，settings.jwt_secret）。

    Args:
        token: JWT 字符串。

    Returns:
        payload 字典（含 sub/role 等声明）。

    Raises:
        ApiError: AUTH_401_TOKEN_EXPIRED / AUTH_401_TOKEN_INVALID。
    """
    settings = get_settings()
    try:
        return dict(
            jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        )
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(ErrorCode.AUTH_401_TOKEN_EXPIRED, "JWT 已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise ApiError(ErrorCode.AUTH_401_TOKEN_INVALID, "JWT 签名校验失败") from exc


async def get_current_user(request: Request) -> dict[str, Any]:
    """当前用户依赖：解析 Authorization Bearer token。

    Args:
        request: HTTP 请求。

    Returns:
        JWT payload（用户声明）。

    Raises:
        ApiError: AUTH_401_TOKEN_INVALID（缺失/非法头）。
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise ApiError(ErrorCode.AUTH_401_TOKEN_INVALID, "缺少 Bearer 凭证")
    return decode_bearer_token(auth_header[len("Bearer ") :])


async def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """admin 角色依赖（RBAC 终检，02 §6）。

    Args:
        user: get_current_user 产出的 payload。

    Returns:
        用户 payload（role=admin）。

    Raises:
        ApiError: AUTH_403_FORBIDDEN（非 admin）。
    """
    if user.get("role") != "admin":
        raise ApiError(ErrorCode.AUTH_403_FORBIDDEN, "仅 admin 可访问")
    return user
