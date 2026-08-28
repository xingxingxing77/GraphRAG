"""契约门禁 openapi_vs_02（09 §4 / 07 §4.2）。

断言：FastAPI OpenAPI 的业务面端点全集与 02 §3/§3.9 双向一致
（架构 §3.6 的 16 端点）。02 §3.11 调试端点随关联单元（1.1 起）
逐个登记至 ALLOWED_EXTRA 并转严格断言。
"""

# --- 本地模块 ---
from app.main import app

# 02 §3.1-§3.8 + §3.9 业务面端点全集（16 个）
REQUIRED_ENDPOINTS: set[tuple[str, str]] = {
    ("POST", "/api/v1/auth/token"),
    ("GET", "/api/v1/sessions"),
    ("GET", "/api/v1/sessions/{session_id}/messages"),
    ("DELETE", "/api/v1/sessions/{session_id}"),
    ("POST", "/api/v1/feedback"),
    ("GET", "/api/v1/graph/subgraph"),
    ("GET", "/api/v1/config/public"),
    ("POST", "/api/v1/chat/precheck"),
    ("POST", "/api/v1/admin/cache/clear"),
    ("POST", "/api/v1/admin/index/rebuild"),
    ("PUT", "/api/v1/admin/config/hot-reload"),
    ("GET", "/api/v1/admin/review-queue"),
    ("POST", "/api/v1/admin/review/decision"),
    ("GET", "/api/v1/admin/tasks/{task_id}"),
    # 02 §3.11 调试端点（随关联单元落地后转入此处登记）
    ("POST", "/api/v1/admin/ingestion/run"),  # 单元 1.1
    ("GET", "/api/v1/admin/ingestion/scans"),  # 单元 1.1
    ("POST", "/api/v1/admin/parsing/preview"),  # 单元 1.2
    ("POST", "/api/v1/admin/cleaning/preview"),  # 单元 1.3
    ("POST", "/api/v1/admin/chunking/preview"),  # 单元 2.1
    ("POST", "/api/v1/admin/debug/embed"),  # 单元 2.3
    ("GET", "/api/v1/admin/communities"),  # 单元 2.6
    ("GET", "/api/v1/admin/qdrant/points"),  # 单元 3.1
    ("GET", "/api/v1/admin/golden/export"),  # 单元 7.2
    ("POST", "/api/v1/admin/debug/analyze"),  # 单元 3.2
    ("POST", "/api/v1/admin/debug/retrieve"),  # 单元 3.3-3.5
    ("POST", "/api/v1/admin/debug/rerank"),  # 单元 4.1
    # 单元 14 prompt-bar（14 1:1 复刻占位端点；写端点已加 JWT 鉴权 M10，
    # 02 §3.12 文字登记待补——先入契约门禁防继续漂移）
    ("GET", "/api/v1/prompt-bar/sources"),
    ("GET", "/api/v1/prompt-bar/commands"),
    ("GET", "/api/v1/prompt-bar/skills"),
    ("POST", "/api/v1/prompt-bar/skills"),
    ("POST", "/api/v1/prompt-bar/skills/upload"),
    ("POST", "/api/v1/prompt-bar/attach"),
    ("POST", "/api/v1/prompt-bar/integrations/{provider}/connect"),
    ("GET", "/health"),
    ("GET", "/ready"),
    ("GET", "/metrics"),  # 单元 3.6
}

# 02 §3.11 调试端点：随关联单元落地后从此集合迁入 REQUIRED_ENDPOINTS
ALLOWED_EXTRA: set[tuple[str, str]] = set()


def _openapi_endpoints() -> set[tuple[str, str]]:
    """提取 OpenAPI schema 中的 (method, path) 全集。"""
    paths = app.openapi()["paths"]
    result: set[tuple[str, str]] = set()
    for path, methods in paths.items():
        for method in methods:
            result.add((method.upper(), path))
    return result


def test_required_endpoints_present() -> None:
    """02 登记的业务面端点在 OpenAPI 中全部存在。"""
    actual = _openapi_endpoints()
    missing = REQUIRED_ENDPOINTS - actual
    assert not missing, f"OpenAPI 缺失 02 登记端点: {sorted(missing)}"


def test_no_undocumented_endpoints() -> None:
    """OpenAPI 中不存在 02 未登记的端点（新端点先登记后实现）。"""
    actual = _openapi_endpoints()
    undocumented = actual - REQUIRED_ENDPOINTS - ALLOWED_EXTRA
    assert not undocumented, f"OpenAPI 存在未登记端点: {sorted(undocumented)}"
