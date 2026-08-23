"""契约门禁 degraded_parity（09 §4）——部分落地。

断言：降级取值枚举的三方一致——
① 02 §2.4 权威表（X-Degraded 七值）；② 06 §9 Banner 文案全覆盖
（由 scripts/doc_consistency_lint.py R1 双向校验承担）；
③ 后端代码可发出的降级值 ⊆ 权威表（本文件承担，待单元 9.1
降级矩阵全量落地后对实际发送点收口断言）。
"""

# --- 标准库 ---
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOC_02 = _REPO_ROOT / "docs" / "02_API接口契约.md"

# 02 §2.4 权威七值（与文档逐值对齐；文档变更由 doc-lint R1 拦截）
CANONICAL_DEGRADED_REASONS: set[str] = {
    "no-graph",
    "no-rerank",
    "llm-fallback",
    "no-memory",
    "no-cache",
    "budget-exhausted",
    "no-persistence",
}


def _doc_degraded_reasons() -> set[str]:
    """解析 02 §2.4 表格首列的降级取值集合。"""
    text = _DOC_02.read_text(encoding="utf-8")
    section = text.split("### 2.4")[1].split("### 2.5")[0]
    return {
        m.group(1)
        for ln in section.splitlines()
        if (m := re.match(r"^\|\s*`([^`]+)`\s*\|", ln))
    }


def test_doc_02_canonical_matches_expected() -> None:
    """02 §2.4 权威表与本门禁常量一致（文档漂移即报警）。"""
    assert _doc_degraded_reasons() == CANONICAL_DEGRADED_REASONS


def test_backend_degraded_literals_within_canonical() -> None:
    """后端代码中出现的 X-Degraded 字面量 ⊆ 权威表。

    扫描 app/ 下形如 X-Degraded 赋值的降级值字面量；
    单元 9.1 降级矩阵落地后此处收口为对实际发送点的断言。
    """
    found: set[str] = set()
    pattern = re.compile(r"[Xx]-[Dd]egraded[^A-Za-z0-9]+([a-z]+-[a-z]+)")
    for py_file in (_REPO_ROOT / "app").rglob("*.py"):
        for m in pattern.finditer(py_file.read_text(encoding="utf-8")):
            found.add(m.group(1))
    unknown = found - CANONICAL_DEGRADED_REASONS
    assert not unknown, f"后端出现未登记降级值: {sorted(unknown)}"
