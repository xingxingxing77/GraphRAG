#!/usr/bin/env python3
# scripts/doc_consistency_lint.py
"""
RAG 文档套件一致性 Lint —— 把"文档即事实 / 命名同源（AGENT.md 约束 6、10）"
工程化为可在 PR 上自动跑的检查。

规则：
  R1 (硬错误, 双向): X-Degraded 枚举一致性。
       - 权威源 = 02_API接口契约.md §2.4 表格列出的全部降级取值（含 llm-fallback / budget-exhausted 等非 no- 前缀）。
       - 正向：任何文档中出现的 `no-*` 降级值必须在该集合内。
       - 反向：06_前端开发指南.md §9 的 Banner 文案表必须覆盖权威源全部取值（防漏）。
  R2 (硬错误): 错误码一致性。
      - 权威源 = 02_API接口契约.md §6 错误码总表。
      - 03/06/07 等文档引用的 `*_NNN_*` 错误码必须存在。
  R3 (软警告): ADR 编号引用合法性。
       - 架构文档 ADR 表中定义的 J/M/D/H/A/B/E/G/P 系列编号视为"已定义"。
       - 其余文档引用的同类编号若不存在于已定义集合，报警告（不阻断）。
  R7 (硬错误, 需 --frontend): 02 §7 TypeScript 类型 <-> 前端 src/types/api.ts 类型名镜像。
  R8 (硬错误, 需 --frontend): 02 §7 AgentNodeName 枚举 <-> 前端 summarize() 分支覆盖。
       （R7/R8 与本脚本已落地的文档级 R1/R2 互补；08 文档另规范了 R4/R5/R6 代码级检查，待后续接入。）

用法：
  python scripts/doc_consistency_lint.py [docs_dir] [--frontend <rag-web 路径>]
退出码：
  1 = 存在 R1/R2/R7/R8 违规；0 = 通过（R3 仅警告时仍 0）。
   （未提供 --frontend 时 R7/R8 软跳过，不计入硬错误）

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
    """加载规范文档。

    G:\\RAG-v0 结构适配: 文档主体在 docs_dir(默认 docs/)，
    少数规约文件(如 AGENT.md)保留在仓库根目录 —— 依次回退查找。
    """
    repo_root = docs_dir.parent
    texts: dict[str, str] = {}
    for name in DOCS:
        p = docs_dir / name
        if not p.exists():
            p = repo_root / name
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
    # §2.4 表格首列的全部降级取值（含 llm-fallback / budget-exhausted 等非 no- 前缀）
    vals: set[str] = set()
    for ln in body.splitlines():
        m = re.match(r"^\|\s*`([^`]+)`\s*\|", ln)
        if m:
            vals.add(m.group(1))
    return vals


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


def r1_reverse_check(texts: dict[str, str], canonical: set[str]) -> list[str]:
    """反向检查：06 §9 Banner 文案须覆盖权威源全部取值（防漏）。"""
    problems: list[str] = []
    t06 = texts.get("06_前端开发指南.md", "")
    sec9 = section(t06, "## 9.", "## 10.")
    covered = {tok for tok in re.findall(r"`([a-z][a-z-]+)`", sec9) if tok in canonical}
    for val in sorted(canonical):
        if val not in covered:
            problems.append(val)
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


# ---------- R7 / R8 (需 --frontend) ----------
def _ts_type_names(text: str) -> set[str]:
    return set(re.findall(r"export\s+(?:interface|type)\s+(\w+)", text))


def r7_doc_types(texts: dict[str, str]) -> set[str]:
    src = texts.get("02_API接口契约.md", "")
    return _ts_type_names(section(src, "## 7.", "## 8."))


def r7_fe_types(frontend: Path) -> set[str] | None:
    p = frontend / "src" / "types" / "api.ts"
    if not p.exists():
        return None
    return _ts_type_names(p.read_text(encoding="utf-8"))


def r7_check(doc_types: set[str], fe_types: set[str] | None) -> list[tuple[str, str]]:
    if fe_types is None:
        return []
    problems: list[tuple[str, str]] = []
    for t in sorted(doc_types - fe_types):
        problems.append(("missing_in_frontend", t))
    for t in sorted(fe_types - doc_types):
        problems.append(("not_in_doc", t))
    return problems


def r8_nodes(texts: dict[str, str]) -> set[str]:
    src = texts.get("02_API接口契约.md", "")
    body = section(src, "## 7.", "## 8.")
    m = re.search(r"export type AgentNodeName\s*=\s*([^;]+);", body)
    if not m:
        return set()
    return set(re.findall(r'"(\w+)"', m.group(1)))


def r8_handled(frontend: Path) -> set[str] | None:
    handled: set[str] = set()
    found = False
    for rel in ("src/hooks/useChatStream.ts", "src/lib/summarize.ts"):
        p = frontend / rel
        if p.exists():
            found = True
            txt = p.read_text(encoding="utf-8")
            handled |= set(re.findall(r'case\s+"(\w+)"', txt))
            handled |= set(re.findall(r'summarize\(\s*"(\w+)"', txt))
    return handled if found else None


def r8_check(nodes: set[str], handled: set[str] | None) -> list[str]:
    if handled is None:
        return []
    return sorted(nodes - handled)


def main() -> int:
    argv = sys.argv[1:]
    docs_dir = Path(__file__).resolve().parent.parent
    frontend: Path | None = None
    rest: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--frontend" and i + 1 < len(argv):
            frontend = Path(argv[i + 1])
            i += 2
            continue
        rest.append(argv[i])
        i += 1
    if rest:
        docs_dir = Path(rest[0])
    texts = load_docs(docs_dir)

    print("== R1: X-Degraded 枚举一致性（双向）==")
    canon = r1_canonical(texts)
    print(f"   权威枚举(02 §2.4): {sorted(canon)}")
    r1 = r1_check(texts, canon)
    for name, val in r1:
        print(f"   [FAIL] {name}: 未知降级值 `{val}`")
    if not r1:
        print("   [ok] 正向: 无未知降级值")
    r1r = r1_reverse_check(texts, canon)
    for val in r1r:
        print(f"   [FAIL] 06 §9 未覆盖权威取值 `{val}`（反向检查）")
    if not r1r:
        print("   [ok] 反向: 06 §9 已覆盖全部权威取值")

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

    # R7 / R8 (gated on --frontend)
    if frontend is not None and not frontend.exists():
        print("== R7/R8: 跳过（--frontend 路径不存在）==")
        r7, r8 = [], []
    elif frontend is not None:
        print("== R7: 02 §7 <-> types/api.ts 类型镜像 ==")
        d7 = r7_doc_types(texts)
        f7 = r7_fe_types(frontend)
        if f7 is None:
            print("   [warn] 未找到 src/types/api.ts，R7 跳过")
            r7 = []
        else:
            r7 = r7_check(d7, f7)
            for kind, t in r7:
                print(f"   [FAIL] R7 {kind}: 类型 `{t}`")
            if not r7:
                print("   [ok] 类型名镜像一致")
        print("== R8: AgentNodeName <-> summarize 覆盖 ==")
        n8 = r8_nodes(texts)
        h8 = r8_handled(frontend)
        if h8 is None:
            print("   [warn] 未找到 useChatStream.ts / summarize.ts，R8 跳过")
            r8 = []
        else:
            r8 = r8_check(n8, h8)
            for node in r8:
                print(f"   [FAIL] R8: 节点 `{node}` 未被 summarize 处理")
            if not r8:
                print("   [ok] 全部 AgentNodeName 均被 summarize 覆盖")
    else:
        print("== R7/R8: 跳过（未指定 --frontend）==")
        r7, r8 = [], []

    hard = len(r1) + len(r2) + len(r1r) + len(r7) + len(r8)
    print(f"\n结果: 硬错误 {hard} 处, 软警告 {len(r3)} 处")
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
