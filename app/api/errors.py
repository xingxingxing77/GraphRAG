"""
错误码常量模块（02 §6 错误码总表的代码侧唯一来源）。

命名空间（02 §6）：AUTH_ 认证 · CHAT_ 聊天链路 · SESSION_ 会话 ·
FEEDBACK_ 反馈 · GRAPH_ 图谱 · ADMIN_ 管理 · SYS_ 系统 · DEBUG_ 调试。
统一错误体形态 {code, message, detail?}（02 §2.3）。

契约门禁 errorcode_parity（09 §4）断言本模块与 02 §6 总表一致；
新增错误码必须先落 02 §6 并同步 06 §9 文案表（AGENT.md §6）。
"""

# --- 标准库 ---
from enum import Enum
from typing import Any

# --- 第三方库 ---
from fastapi import HTTPException


class ErrorCode(str, Enum):
    """02 §6 错误码总表全集（与文档逐项对齐）。"""

    # --- AUTH_ 认证 ---
    AUTH_400_BAD_CREDENTIALS = "AUTH_400_BAD_CREDENTIALS"
    AUTH_401_INVALID_API_KEY = "AUTH_401_INVALID_API_KEY"
    AUTH_401_TOKEN_EXPIRED = "AUTH_401_TOKEN_EXPIRED"
    AUTH_401_TOKEN_INVALID = "AUTH_401_TOKEN_INVALID"
    AUTH_403_FORBIDDEN = "AUTH_403_FORBIDDEN"
    AUTH_429_RATE_LIMITED = "AUTH_429_RATE_LIMITED"

    # --- CHAT_ 聊天链路 ---
    CHAT_400_EMPTY_QUERY = "CHAT_400_EMPTY_QUERY"
    CHAT_400_INVALID_TIER = "CHAT_400_INVALID_TIER"
    CHAT_404_THREAD_NOT_FOUND = "CHAT_404_THREAD_NOT_FOUND"
    CHAT_429_RATE_LIMITED = "CHAT_429_RATE_LIMITED"
    CHAT_504_TIER_TIMEOUT = "CHAT_504_TIER_TIMEOUT"

    # --- SESSION_ 会话 ---
    SESSION_404_NOT_FOUND = "SESSION_404_NOT_FOUND"

    # --- FEEDBACK_ 反馈 ---
    FEEDBACK_404_MESSAGE_NOT_FOUND = "FEEDBACK_404_MESSAGE_NOT_FOUND"

    # --- GRAPH_ 图谱 ---
    GRAPH_404_ENTITY_NOT_FOUND = "GRAPH_404_ENTITY_NOT_FOUND"
    GRAPH_503_STORE_UNAVAILABLE = "GRAPH_503_STORE_UNAVAILABLE"

    # --- ADMIN_ 管理 ---
    ADMIN_409_TASK_RUNNING = "ADMIN_409_TASK_RUNNING"

    # --- SYS_ 系统 ---
    SYS_400_VALIDATION = "SYS_400_VALIDATION"
    SYS_403_DEBUG_DISABLED = "SYS_403_DEBUG_DISABLED"
    SYS_404_NOT_FOUND = "SYS_404_NOT_FOUND"
    SYS_500_INTERNAL = "SYS_500_INTERNAL"
    SYS_503_DEPENDENCY_DOWN = "SYS_503_DEPENDENCY_DOWN"

    # --- DEBUG_ 调试 ---
    DEBUG_400_INVALID_SOURCE = "DEBUG_400_INVALID_SOURCE"


_STATUS_MAP: dict[ErrorCode, int] = {
    ErrorCode.AUTH_400_BAD_CREDENTIALS: 400,
    ErrorCode.AUTH_401_INVALID_API_KEY: 401,
    ErrorCode.AUTH_401_TOKEN_EXPIRED: 401,
    ErrorCode.AUTH_401_TOKEN_INVALID: 401,
    ErrorCode.AUTH_403_FORBIDDEN: 403,
    ErrorCode.AUTH_429_RATE_LIMITED: 429,
    ErrorCode.CHAT_400_EMPTY_QUERY: 400,
    ErrorCode.CHAT_400_INVALID_TIER: 400,
    ErrorCode.CHAT_404_THREAD_NOT_FOUND: 404,
    ErrorCode.CHAT_429_RATE_LIMITED: 429,
    ErrorCode.CHAT_504_TIER_TIMEOUT: 504,
    ErrorCode.SESSION_404_NOT_FOUND: 404,
    ErrorCode.FEEDBACK_404_MESSAGE_NOT_FOUND: 404,
    ErrorCode.GRAPH_404_ENTITY_NOT_FOUND: 404,
    ErrorCode.GRAPH_503_STORE_UNAVAILABLE: 503,
    ErrorCode.ADMIN_409_TASK_RUNNING: 409,
    ErrorCode.SYS_400_VALIDATION: 400,
    ErrorCode.SYS_403_DEBUG_DISABLED: 403,
    ErrorCode.SYS_404_NOT_FOUND: 404,
    ErrorCode.SYS_500_INTERNAL: 500,
    ErrorCode.SYS_503_DEPENDENCY_DOWN: 503,
    ErrorCode.DEBUG_400_INVALID_SOURCE: 400,
}


def status_of(code: ErrorCode) -> int:
    """从错误码解析 HTTP 状态码（显式映射，P1 M-10，避免脆弱字符串解析）。

    Args:
        code: 错误码枚举成员。

    Returns:
        HTTP 状态码整数。
    """
    return _STATUS_MAP.get(code, int(code.value.split("_")[1]))


class ApiError(HTTPException):
    """统一错误体异常（02 §2.3）。

    经全局异常处理器转为 {code, message, detail} JSON 响应；
    降级场景另经响应头 X-Degraded 透传（02 §2.4，不属错误体）。

    Attributes:
        code: 02 §6 登记的错误码。
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        detail: Any = None,
    ) -> None:
        """初始化统一错误体异常。

        Args:
            code: 错误码（决定 HTTP 状态码）。
            message: 面向用户的错误消息。
            detail: 调试细节（可选）。
        """
        super().__init__(status_code=status_of(code), detail=detail)
        self.code = code
        self.message = message
