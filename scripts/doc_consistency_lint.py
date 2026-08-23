#!/usr/bin/env python3
# scripts/doc_consistency_lint.py
"""
RAG 文档套件一致性 Lint —— 把"文档即事实 / 命名同源（AGENT.md 约束 6、10）"
工程化为可在 PR 上自动跑的检查。

规则：
  R1 (硬错误): X-Degraded 枚举一致性。
      - 权威源 = 02_API接口契约.md §2.4 表格列出的 `no-*` 取值。
      - 任何文档中出现的 `no-*` 降级值必须在该集合内。
  R2 (硬错误): 错误码一致性。
      - 权威源 = 02_API接口契约.md §6 错误码总表。
      - 03/06/07 等文档引用的 `*_NNN_*` 错误码必须存在。
  R3 (软警告): ADR 编号引用合法性。
      - 架构文档 ADR 表中定义的 J/M/D/H/A/B/E/G/P 系列编号视为"已定义"。
      - 其余文档引用的同类编号若不存在于已定义集合，报警告（不阻断）。

用法：
  python scripts/doc_consistency_lint.py [docs_dir]
退出码：
  1 = 存在 R1/R2 违规；0 = 通过（R3 仅警告时仍 0）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DOCS = [
    "README.md",
    "AGENT.md",
    "02_API接口契约.md",
    "03_通信协议规范.md",
    "04_数据库设计.md",
    "05_后端开发指南.md",
    "06_前端开发指南.md",
    "07_联调与测试计划.md",
    "GraphRAG_系统架构文档.md",
]

# R3 中不属于 ADR 但合法出现、需豁免的编号式记号
R3_DENY = {"P50", "P90", "P95", "P99"}  # 延迟指标，非 ADR
R3_ALLOW_PREFIX = ("F", "L", "S-", "A-", "H-", "M-", "D-", "E-")  # 测试/联调/里程碑编号

ADR_SERIES = "[JMDHABEGP]"


def load_docs(docs_dir: Path) -> dict[str, str]:
    texts: dict[str, str] = {}
    for name in DOCS:
        p = docs_dir / name
        if p.exists():
            texts[name] = p.read_text(encoding="utf-8")
        else:
            print(f"[warn] 缺少文档: {name}")
    return texts


def section(text: str, start: str, end: str) -> str:
    """截取 text 中 start 行到 end 行之间的内容（不含 end 行）。"""
    lines = text.splitlines()
    buf, capturing = [], False
    for ln in lines:
        if start in ln:
            capturing = True
            continue
        if end in ln:
            break
        if capturing:
            buf.append(ln)
    return "\n".join(buf)


# ---------- R1 ----------
def r1_canonical(texts: dict[str, str]) -> set[str]:
    src = texts.get("02_API接口契约.md", "")
    body = section(src, "### 2.4", "### 2.5")
    return set(re.findall(r"`(no-[a-z-]+)`", body))


def r1_check(texts: dict[str, str], canonical: set[str]) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    pat = re.compile(r"`?(no-[a-z-]+)`?")
    for name, txt in texts.items():
        if name == "02_API接口契约.md":
            continue
        for m in pat.finditer(txt):
            val = m.group(1)
            if val not in canonical:
                problems.append((name, val))
    return problems


# ---------- R2 ----------
def r2_canonical(texts: dict[str, str]) -> set[str]:
    src = texts.get("02_API接口契约.md", "")
    body = section(src, "## 6.", "## 7.")
    codes = set()
    for ln in body.splitlines():
        m = re.match(r"^\|\s*([A-Z][A-Z_]*_\d{3}_[A-Z_]+)\s*\|", ln)
        if m:
            codes.add(m.group(1))
    return codes


def r2_check(texts: dict[str, str], canonical: set[str]) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    pat = re.compile(r"\b([A-Z][A-Z_]*_\d{3}_[A-Z_]+)\b")
    for name, txt in texts.items():
        if name == "02_API接口契约.md":
            continue
        for m in pat.finditer(txt):
            code = m.group(1)
            if code not in canonical:
                problems.append((name, code))
    return problems


# ---------- R3 ----------
def r3_defined(texts: dict[str, str]) -> set[str]:
    src = texts.get("GraphRAG_系统架构文档.md", "")
    defined = set()
    for ln in src.splitlines():
        m = re.match(rf"^\|\s*({ADR_SERIES}\d+)\s*\|", ln)
        if m:
            defined.add(m.group(1))
    # 管道阶段 P1-P7 与图谱构建步骤 G1-G5 在架构正文（非 ADR 表）中定义，预置避免误报
    defined.update(f"P{i}" for i in range(1, 8))
    defined.update(f"G{i}" for i in range(1, 6))
    return defined


def r3_check(texts: dict[str, str], defined: set[str]) -> list[tuple[str, str]]:
    warnings: list[tuple[str, str]] = []
    pat = re.compile(rf"\b({ADR_SERIES}\d+)\b")
    for name, txt in texts.items():
        if name == "GraphRAG_系统架构文档.md":
            continue
        for m in pat.finditer(txt):
            token = m.group(1)
            if token in R3_DENY:
                continue
            if token not in defined:
                warnings.append((name, token))
    return warnings


def main() -> int:
    docs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    texts = load_docs(docs_dir)

    print("== R1: X-Degraded 枚举一致性 ==")
    canon = r1_canonical(texts)
    print(f"   权威枚举(02 §2.4): {sorted(canon)}")
    r1 = r1_check(texts, canon)
    for name, val in r1:
        print(f"   [FAIL] {name}: 未知降级值 `{val}`")
    if not r1:
        print("   [ok] 无未知降级值")

    print("== R2: 错误码一致性 ==")
    codes = r2_canonical(texts)
    print(f"   权威错误码数(02 §6): {len(codes)}")
    r2 = r2_check(texts, codes)
    for name, code in r2:
        print(f"   [FAIL] {name}: 引用未定义错误码 `{code}`")
    if not r2:
        print("   [ok] 无未定义错误码引用")

    print("== R3: ADR 编号引用（软警告）==")
    defined = r3_defined(texts)
    print(f"   已定义 ADR 数(架构文档): {len(defined)}")
    r3 = r3_check(texts, defined)
    for name, tok in r3:
        print(f"   [warn] {name}: 引用未定义编号 `{tok}`")
    if not r3:
        print("   [ok] 无未定义编号引用")

    hard = len(r1) + len(r2)
    print(f"\n结果: 硬错误 {hard} 处, 软警告 {len(r3)} 处")
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
