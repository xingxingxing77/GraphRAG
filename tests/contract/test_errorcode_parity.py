"""契约门禁 errorcode_parity（09 §4 / 08 R5 前置）。

断言：代码侧错误码全集（app/api/errors.py ErrorCode）与
02 §6 错误码总表双向一致——后端不会抛出文档未登记的错误码，
文档登记的错误码均有代码常量可引用。
"""

# --- 标准库 ---
import re
from pathlib import Path

# --- 本地模块 ---
from app.api.errors import ErrorCode

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOC_02 = _REPO_ROOT / "docs" / "02_API接口契约.md"


def _doc_error_codes() -> set[str]:
    """解析 02 §6 错误码总表首列的错误码集合。"""
    text = _DOC_02.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("## 6. 错误码总表"))
    codes: set[str] = set()
    for ln in lines[start:]:
        if ln.startswith("## ") and not ln.startswith("## 6"):
            break
        m = re.match(r"^\|\s*([A-Z]+_\d{3}_[A-Z0-9_]+)\s*\|", ln)
        if m:
            codes.add(m.group(1))
    return codes


def test_doc_02_error_table_parseable() -> None:
    """前置：02 §6 总表可解析且非空。"""
    assert len(_doc_error_codes()) >= 20


def test_code_subset_of_doc() -> None:
    """后端可抛错误码 ⊆ 02 §6 总表（不抛文档未登记的码）。"""
    doc_codes = _doc_error_codes()
    code_codes = {m.value for m in ErrorCode}
    assert code_codes <= doc_codes, f"代码中存在未登记错误码: {code_codes - doc_codes}"


def test_doc_subset_of_code() -> None:
    """02 §6 总表 ⊆ 后端错误码常量（文档登记的码代码可引用）。"""
    doc_codes = _doc_error_codes()
    code_codes = {m.value for m in ErrorCode}
    assert doc_codes <= code_codes, f"文档登记但代码缺常量: {doc_codes - code_codes}"
