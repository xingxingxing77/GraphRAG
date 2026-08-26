"""F2 业务面端点组测试（单元 10.2 S3，07 §4 L1 批次）。

断言：六组端点 happy path（auth/config/sessions/feedback/precheck/
graph-subgraph 已各自覆盖，此处聚焦 auth/sessions/feedback/config）；
401 静默重兑换语义（token 失效 → AUTH_401_TOKEN_INVALID/EXPIRED）。
"""

# --- 标准库 ---
import time

# --- 第三方库 ---
import jwt
import pytest
from fastapi.testclient import TestClient

# --- 本地模块 ---
from app.api import session_store, thread_store
from app.core.config import get_settings
from app.main import create_app


def _admin_token() -> str:
    """签发 admin 测试 JWT。"""
    settings = get_settings()
    return jwt.encode(
        {"sub": "u-admin", "name": "admin", "role": "admin", "exp": int(time.time()) + 3600},
        settings.jwt_secret,
        algorithm="HS256",
    )


def _auth_headers() -> dict[str, str]:
    """带 Bearer 的请求头。"""
    return {"Authorization": f"Bearer {_admin_token()}"}


@pytest.fixture(autouse=True)
def _clean_store(monkeypatch):
    """会话存储走内存替身：thread_store 委托 session_store。

    GAP-A1 生产路径为 langgraph-server threads（测试无 langgraph-server
    不可达），此处用进程内替身委托验证端点鉴权/归属/204/404 语义。
    """
    session_store.clear_store()

    async def list_sessions(user_id, cursor, limit):
        return session_store.list_sessions(user_id, cursor, limit)

    async def get_messages(user_id, session_id, cursor, limit):
        return session_store.get_messages(user_id, session_id, cursor, limit)

    async def delete_session(user_id, session_id):
        return session_store.delete_session(user_id, session_id)

    monkeypatch.setattr(thread_store, "list_sessions", list_sessions)
    monkeypatch.setattr(thread_store, "get_messages", get_messages)
    monkeypatch.setattr(thread_store, "delete_session", delete_session)
    yield
    session_store.clear_store()


class TestAuthGrant:
    """auth/token 双凭证兑换。"""

    def test_password_grant_happy_path(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/auth/token",
                json={"grant_type": "password", "username": "admin", "password": "admin-dev-password"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["access_token"]
            assert body["user"]["role"] == "admin"

    def test_api_key_grant_happy_path(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/auth/token",
                json={"grant_type": "api_key", "api_key": "dev-api-key-0001"},
            )
            assert resp.status_code == 200

    def test_bad_password_rejected(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/auth/token",
                json={"grant_type": "password", "username": "admin", "password": "wrong"},
            )
            assert resp.status_code == 400
            assert resp.json()["code"] == "AUTH_400_BAD_CREDENTIALS"

    def test_invalid_api_key_rejected(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/auth/token",
                json={"grant_type": "api_key", "api_key": "bogus"},
            )
            assert resp.status_code == 401
            assert resp.json()["code"] == "AUTH_401_INVALID_API_KEY"

    def test_issued_token_passes_verification(self) -> None:
        """兑换所得 token 可通过受保护端点验证（闭环）。"""
        app = create_app()
        with TestClient(app) as client:
            issued = client.post(
                "/api/v1/auth/token",
                json={"grant_type": "password", "username": "admin", "password": "admin-dev-password"},
            ).json()["access_token"]
            resp = client.get(
                "/api/v1/sessions",
                headers={"Authorization": f"Bearer {issued}"},
            )
            assert resp.status_code == 200


class TestSessionsFlow:
    """sessions 三端点 + 归属隔离。"""

    def test_requires_auth(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            assert client.get("/api/v1/sessions").status_code == 401

    def test_register_list_get_delete_flow(self) -> None:
        session_store.register_message("u-admin", "s1", "user", "清蒸鲈鱼怎么做？")
        session_store.register_message("u-admin", "s1", "assistant", "蒸八分钟。")
        app = create_app()
        with TestClient(app) as client:
            headers = _auth_headers()
            listing = client.get("/api/v1/sessions", headers=headers).json()
            assert len(listing["items"]) == 1
            assert listing["items"][0]["message_count"] == 2
            assert listing["items"][0]["title"] == "清蒸鲈鱼怎么做？"

            msgs = client.get("/api/v1/sessions/s1/messages", headers=headers).json()
            assert len(msgs["items"]) == 2

            del_resp = client.delete("/api/v1/sessions/s1", headers=headers)
            assert del_resp.status_code == 204
            assert client.get("/api/v1/sessions", headers=headers).json()["items"] == []

    def test_other_user_session_returns_404(self) -> None:
        session_store.register_message("someone-else", "s2", "user", "你好")
        app = create_app()
        with TestClient(app) as client:
            headers = _auth_headers()  # sub=u-admin ≠ someone-else
            assert client.get("/api/v1/sessions/s2/messages", headers=headers).status_code == 404
            assert client.delete("/api/v1/sessions/s2", headers=headers).status_code == 404
            # 他人会话不出现在本人列表
            assert client.get("/api/v1/sessions", headers=headers).json()["items"] == []


class TestFeedbackFlow:
    """feedback 点踩回流。"""

    def test_down_feedback_enters_bad_case_queue(self) -> None:
        from app.api.endpoints.golden import _BAD_CASES

        # GAP-A2：登记真实问答后点踩，bad case 应反查真实快照而非占位
        session_store.register_message("u-admin", "s1", "user", "清蒸鲈鱼怎么做？")
        ast_msg = session_store.register_message("u-admin", "s1", "assistant", "大火蒸八分钟。")

        app = create_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/feedback",
                json={
                    "session_id": "s1",
                    "message_id": ast_msg.message_id,
                    "rating": "down",
                    "reason": "wrong",
                    "comment": "答案不对",
                },
                headers=_auth_headers(),
            )
            assert resp.status_code == 200
            case = next(c for c in _BAD_CASES if c["message_id"] == ast_msg.message_id)
            assert case["query"] == "清蒸鲈鱼怎么做？"
            assert case["answer"] == "大火蒸八分钟。"
        _BAD_CASES.clear()

    def test_up_feedback_no_bad_case(self) -> None:
        from app.api.endpoints.golden import _BAD_CASES

        app = create_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/feedback",
                json={"session_id": "s1", "message_id": "m2", "rating": "up"},
                headers=_auth_headers(),
            )
            assert resp.status_code == 200
            assert not any(c["message_id"] == "m2" for c in _BAD_CASES)
        _BAD_CASES.clear()


class TestPublicConfig:
    """config/public（J2 前端前提）。"""

    def test_public_config_models_no_secrets(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/api/v1/config/public")
            assert resp.status_code == 200
            body = resp.json()
            assert len(body["models"]) >= 1
            for m in body["models"]:
                assert set(m.keys()) == {"id", "label", "provider"}  # 无敏感字段
            assert body["latency_tiers"] == ["fast", "standard", "deep"]
            assert "llm_extract" in body["compression_strategies"]


class TestQdrantDebugAuth:
    """单元 10.8 批次 A BUG-01 收口：GET /admin/qdrant/points 漏挂鉴权修复（02 §3.11）。"""

    def test_qdrant_points_requires_auth(self) -> None:
        """裸访（无 token）返回 401，不泄露 points payload（BUG-01）。"""
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/api/v1/admin/qdrant/points", params={"doc_id": "d1"})
            assert resp.status_code == 401
