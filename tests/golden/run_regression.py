#!/usr/bin/env python3
"""golden set 回归脚本（D8 · 07 §8 · 单元 7.2）。

评估口径（离线词法 Recall@5，CI 无外部依赖）：对每条用例以查询
词元与期望文档内容的重叠率近似召回命中；在线向量评估随 10.x
联调接线。阻断阈值：Recall@5 相对基线下降 >3% → 退出码非零。

触发条件（CI 自动）：分块参数 / 清洗规则 / embedding 或 reranker
升级 / 索引重建 的 PR。

用法:
    python tests/golden/run_regression.py --suite v1 [--freeze-baseline]
"""
from __future__ import annotations

# --- 标准库 ---
import argparse
import json
import re
import sys
from pathlib import Path

# --- 第三方库 ---
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_DIR = Path(__file__).resolve().parent

# 阻断阈值（07 §8）：Recall@5 相对基线下降超过该值即阻断
_BLOCK_DELTA = 0.03

# 词元切分（中文按字，英文按词）
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+")


def load_golden_set(suite: str) -> list[dict[str, str]]:
    """加载 golden set 用例。

    Args:
        suite: 套件版本（如 v1）。

    Returns:
        用例列表。

    Raises:
        SystemExit: 套件文件缺失。
    """
    path = _GOLDEN_DIR / suite / "golden_set.yaml"
    if not path.exists():
        raise SystemExit(f"[golden] 套件缺失: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return list(data.get("entries") or [])


def _tokens(text: str) -> set[str]:
    """切分词元集合（停用单字虚词不计）。

    Args:
        text: 输入文本。

    Returns:
        词元集合。
    """
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1 or "\u4e00" <= t <= "\u9fff"}


def lexical_recall_hit(query: str, doc_path: str, top_k: int = 5) -> float:
    """离线词法召回近似：查询词元在期望文档中的覆盖率。

    Args:
        query: 查询文本。
        doc_path: 期望文档仓库相对路径。
        top_k: 口径占位（在线模式为召回窗口）。

    Returns:
        覆盖率 [0,1]（文档缺失记 0）。
    """
    abs_path = _REPO_ROOT / doc_path
    if not abs_path.exists():
        return 0.0
    content = abs_path.read_text(encoding="utf-8")
    q_tokens = _tokens(query.replace("的做法", ""))
    if not q_tokens:
        return 0.0
    d_tokens = _tokens(content)
    return len(q_tokens & d_tokens) / len(q_tokens)


def evaluate(entries: list[dict[str, str]]) -> dict[str, float]:
    """评估全部用例。

    Args:
        entries: 用例列表。

    Returns:
        指标字典 {recall_at_5, count}。
    """
    if not entries:
        return {"recall_at_5": 0.0, "count": 0}
    total = sum(lexical_recall_hit(e["query"], e["expected_doc"]) for e in entries)
    return {"recall_at_5": total / len(entries), "count": float(len(entries))}


def baseline_path(suite: str) -> Path:
    """基线文件路径。

    Args:
        suite: 套件版本。

    Returns:
        baseline.json 路径。
    """
    return _GOLDEN_DIR / suite / "baseline.json"


def main() -> int:
    """命令行入口。

    Returns:
        0 通过；1 阻断（相对基线下降 >3%）或评估失败。
    """
    parser = argparse.ArgumentParser(description="golden set 回归（D8）")
    parser.add_argument("--suite", default="v1", help="golden set 版本")
    parser.add_argument("--report", default=None, help="报告输出路径（JSON）")
    parser.add_argument(
        "--freeze-baseline", action="store_true", help="冻结当前指标为基线"
    )
    args = parser.parse_args()

    entries = load_golden_set(args.suite)
    metrics = evaluate(entries)
    print(
        f"[golden] suite={args.suite} entries={int(metrics['count'])} "
        f"recall@5={metrics['recall_at_5']:.4f}"
    )

    if args.report:
        Path(args.report).write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    bl_path = baseline_path(args.suite)
    if args.freeze_baseline:
        bl_path.write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[golden] 基线已冻结: {bl_path}")
        return 0

    if not bl_path.exists():
        print("[golden] 无基线，跳过阻断判定（先 --freeze-baseline）")
        return 0

    baseline = json.loads(bl_path.read_text(encoding="utf-8"))
    delta = baseline.get("recall_at_5", 0.0) - metrics["recall_at_5"]
    print(f"[golden] 基线 recall@5={baseline.get('recall_at_5', 0):.4f} delta={delta:+.4f}")
    if delta > _BLOCK_DELTA:
        print(f"[golden] 阻断：Recall@5 相对基线下降 {delta:.4f} > {_BLOCK_DELTA}（D8）")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
