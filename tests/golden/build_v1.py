#!/usr/bin/env python3
"""golden set v1 构建脚本（D8 · 07 §8 · 单元 7.2）。

从 menu/HowToCook 菜单树确定性生成 golden_set.yaml（50-100 条）：
每道菜一条查询用例（query=菜名做法、expected_doc=菜谱相对路径）。
基线冻结后将本文件产物纳入版本管理；重建须重新冻结基线。

用法:
    python tests/golden/build_v1.py
"""
from __future__ import annotations

# --- 标准库 ---
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MENU_DIR = _REPO_ROOT / "menu" / "HowToCook" / "dishes"
_OUT_PATH = Path(__file__).resolve().parent / "v1" / "golden_set.yaml"

# 版本化规模约束（07 §8：50-100 条）
_MAX_ENTRIES = 80


def collect_entries() -> list[dict[str, str]]:
    """扫描菜单树收集用例。

    Returns:
        [{id, query, expected_doc, category}, ...] 按路径排序。
    """
    entries: list[dict[str, str]] = []
    for md_file in sorted(_MENU_DIR.rglob("*.md")):
        rel = md_file.relative_to(_REPO_ROOT).as_posix()
        dish = md_file.stem
        if dish in ("示例菜", "README"):
            continue
        category = md_file.parent.parent.name if md_file.parent.name != "dishes" else md_file.parent.name
        entries.append(
            {
                "id": f"g{len(entries) + 1:03d}",
                "query": f"{dish}的做法",
                "expected_doc": rel,
                "category": category,
            }
        )
        if len(entries) >= _MAX_ENTRIES:
            break
    return entries


def render_yaml(entries: list[dict[str, str]]) -> str:
    """渲染 golden set YAML 文本。

    Args:
        entries: 用例列表。

    Returns:
        YAML 文本。
    """
    lines = [
        "# golden set v1（D8 · 07 §8 · 单元 7.2）",
        "# 由 tests/golden/build_v1.py 从 menu/HowToCook 确定性生成；",
        "# 回归指标与阻断阈值见 run_regression.py（Recall@5 相对基线降 >3% 阻断）。",
        "version: v1",
        "entries:",
    ]
    for e in entries:
        lines.append(f"  - id: {e['id']}")
        lines.append(f"    query: \"{e['query']}\"")
        lines.append(f"    expected_doc: \"{e['expected_doc']}\"")
        lines.append(f"    category: \"{e['category']}\"")
    return "\n".join(lines) + "\n"


def main() -> int:
    """构建入口。"""
    entries = collect_entries()
    if not 50 <= len(entries) <= 100:
        print(f"[golden] 用例数 {len(entries)} 超出 50-100 约束", file=sys.stderr)
        return 1
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OUT_PATH.write_text(render_yaml(entries), encoding="utf-8")
    print(f"[golden] 已生成 {_OUT_PATH}（{len(entries)} 条）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
