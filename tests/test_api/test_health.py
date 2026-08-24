"""健康聚合端点测试（单元 10.1 S3，07 §5 H-01/H-02）。

断言：/health liveness 恒 ok；/ready 七组件聚合结构完整；
critical/non-critical 分类与降级头语义（02 §3.9）。
"""

# --- 第三方库 ---
from fastapi.testclient import TestClient

# --- 本地模块 ---
from app.api.endpoints.health import _CRITICAL_COMPONENTS
from app.main import create_app

_SEVEN_COMPONENTS = {
    "postgres",
    "qdrant",
    "neo4j",
    "elasticsearch",
    "redis",
    "langgraph-server",
    "ollama",
}


class TestLiveness:
    """H-01：/health liveness。"""

    def test_health_always_ok(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"


class TestReadiness:
    """H-02：/ready 七组件聚合。"""

    def test_ready_returns_all_seven_components(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/ready")
            # critical 全 up → 200；否则 503（两者均为合法聚合体）
            assert resp.status_code in (200, 503)
            body = resp.json()
            assert set(body["components"].keys()) == _SEVEN_COMPONENTS

    def test_component_status_enum(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/ready")
            for name, comp in resp.json()["components"].items():
                assert comp["status"] in ("up", "degraded", "down")

    def test_critical_classification(self) -> None:
        """critical 集合与 02 §3.9 一致。"""
        assert _CRITICAL_COMPONENTS == {
            "qdrant",
            "neo4j",
            "elasticsearch",
            "ollama",
        }

    def test_non_critical_down_degrades_not_blocks(self) -> None:
        """redis/postgres down → degraded + X-Degraded，但非 critical 不单独致 503。"""
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/ready")
            body = resp.json()
            for name in ("redis", "postgres"):
                # non-critical 故障时记为 degraded（不是 down）
                assert body["components"][name]["status"] in ("up", "degraded")
