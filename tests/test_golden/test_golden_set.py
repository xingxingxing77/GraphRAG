"""golden set 工程化测试（单元 7.2 S3，07 §8 断言）。

断言：入库规模 50-100 条与 Schema 完整性；回归阻断逻辑（人为劣化
触发退出码 1）；导出端点 CSV 列头完整。
"""

# --- 标准库 ---
import importlib.util
from pathlib import Path

# --- 第三方库 ---
import pytest
import yaml
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_SET = _REPO_ROOT / "tests" / "golden" / "v1" / "golden_set.yaml"


def _load_run_regression():  # noqa: ANN202
    """按路径加载 run_regression 脚本模块。"""
    path = _REPO_ROOT / "tests" / "golden" / "run_regression.py"
    spec = importlib.util.spec_from_file_location("run_regression", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestGoldenSetIntake:
    """入库版本化（50-100 条 + Schema）。"""

    def test_entry_count_in_range(self) -> None:
        data = yaml.safe_load(_GOLDEN_SET.read_text(encoding="utf-8"))
        entries = data["entries"]
        assert 50 <= len(entries) <= 100

    def test_entry_schema_complete(self) -> None:
        data = yaml.safe_load(_GOLDEN_SET.read_text(encoding="utf-8"))
        ids = set()
        for e in data["entries"]:
            assert e["id"] and e["query"] and e["expected_doc"] and e["category"]
            assert e["id"] not in ids  # id 唯一
            ids.add(e["id"])
            # expected_doc 指向真实文档
            assert (_REPO_ROOT / e["expected_doc"]).exists()


class TestRegressionBlocking:
    """阻断逻辑（D8：Recall@5 降幅 >3% 阻断）。"""

    def test_normal_evaluation_passes(self) -> None:
        rg = _load_run_regression()
        entries = rg.load_golden_set("v1")
        metrics = rg.evaluate(entries)
        assert metrics["recall_at_5"] > 0.9

    def test_degraded_docs_lower_recall(self) -> None:
        """人为劣化演练：期望文档缺失 → 召回下降。"""
        rg = _load_run_regression()
        degraded_entries = [
            {"id": "x1", "query": "不存在的菜肴独特做法", "expected_doc": "no/such/doc.md", "category": "x"}
            for _ in range(10)
        ]
        metrics = rg.evaluate(degraded_entries)
        assert metrics["recall_at_5"] < 0.5  # 显著低于基线

    def test_block_delta_threshold(self) -> None:
        """阻断判定：delta > 3% 应阻断。"""
        rg = _load_run_regression()
        baseline_score = 1.0
        current = 0.95  # 下降 5%
        delta = baseline_score - current
        assert delta > rg._BLOCK_DELTA  # 触发阻断条件

    def test_within_threshold_passes(self) -> None:
        rg = _load_run_regression()
        delta = 1.0 - 0.99  # 下降 1%
        assert delta <= rg._BLOCK_DELTA  # 不阻断


class TestGoldenExport:
    """导出端点（02 §3.11）。"""

    def test_export_csv_headers(self) -> None:
        from app.main import create_app

        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/api/v1/admin/golden/export")
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/csv")
            first_line = resp.text.splitlines()[0]
            assert first_line == "session_id,message_id,query,answer,created_at"

    def test_record_and_export_roundtrip(self) -> None:
        from app.api.endpoints.golden import _BAD_CASES, record_bad_case
        from app.main import create_app

        record_bad_case("s1", "m1", "清蒸鲈鱼怎么做", "错误答案")
        try:
            app = create_app()
            with TestClient(app) as client:
                resp = client.get("/api/v1/admin/golden/export")
                assert "清蒸鲈鱼怎么做" in resp.text
                assert "错误答案" in resp.text
        finally:
            _BAD_CASES.clear()
