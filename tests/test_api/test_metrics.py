"""/metrics 指标存在性测试（单元 3.6 S3，07 §5 断言）。

断言：GET /metrics 返回 05 §7 五项指标族；检索器错误上报后
rag_retrieval_errors_total 按 source 打标。
"""

# --- 第三方库 ---
from fastapi.testclient import TestClient

# --- 本地模块 ---
from app.api.metrics import record_retrieval_error
from app.main import create_app


class TestMetricsEndpoint:
    """/metrics 指标存在性检查。"""

    def test_metrics_exposes_five_families(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/metrics")
            assert resp.status_code == 200
            body = resp.text
            assert "rag_request_duration_seconds" in body
            assert "rag_retrieval_errors_total" in body
            assert "rag_llm_tokens_total" in body
            assert "rag_degraded_total" in body
            assert "rag_agent_rounds" in body

    def test_retrieval_error_metric_labeled_by_source(self) -> None:
        record_retrieval_error("dense", 1)
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/metrics")
            assert 'rag_retrieval_errors_total{source="dense"}' in resp.text

    def test_zero_count_not_reported(self) -> None:
        """count=0 不产生标签序列。"""
        record_retrieval_error("__never_source__", 0)
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/metrics")
            assert "__never_source__" not in resp.text
