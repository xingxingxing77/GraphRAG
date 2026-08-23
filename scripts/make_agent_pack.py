#!/usr/bin/env python3
# scripts/make_agent_pack.py
"""
派发包（Context Pack）生成器（09 §1）。

按 01 §6 单元的「前置阅读」章节引用，从文档套件抽取拼成
agent-pack-<x.y>.md，供编码 Agent 消费——只给作用域上下文，不丢整库。

用法:
    python scripts/make_agent_pack.py 1.1 [-o out_dir]
退出码:
    0 = 生成成功；1 = 单元不存在或文档缺失。
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_01 = REPO_ROOT / "docs" / "01_开发流程.md"
AGENT_MD = REPO_ROOT / "AGENT.md"

# 01 §6 单元行格式: > **1.1 P1 采集层（Ingestion）**
UNIT_HEADER_RE = re.compile(r"^>\s*\*\*(\d+\.\d+)\s+(.+?)\*\*\s*$")
# S1/S2/S3 行中的〔前置阅读〕引用
PREREAD_RE = re.compile(r"〔(.+?)〕")

HARD_CONSTRAINTS = """\
- 契约唯一来源（D1）：跨层字段只定义在 app/core/models.py
- 缓冲式流（M1）：standard/deep 校验完成前不流出答案文本
- 降级不抛错（M3/D5）：超限与依赖故障走降级作答 + X-Degraded 标注
- async 三铁律（05 §3.3）：同步推理包 executor / GPU 过 semaphore / 外部调用独立超时
- 循环必有终止预算（M3）：新增回环登记 max 次数与超限行为
- 命名同源：端点/错误码只认 02；Collection/Index/Key 只认 04
- 密钥纪律（J16/D7）：api_key 只经环境变量，禁止明文入代码/日志/前端 bundle
- 图谱写入幂等（G4/J12）：MERGE canonical_name；开放区走 admin 审核流
- 决策引用：注释/PR 引用决策编号（如 J20/E3），不重新发明论证
- 文档即事实：实现与文档不符当天提文档修正 PR
- 设计系统约束（J24）：banned 依赖禁止；颜色/阴影/圆角仅经 globals.css 令牌
"""

WORKFLOW_TEMPLATE = """\
- S1 后端：先完整读取前置阅读 → 再写代码；契约改动先落 app/core/models.py
  并同 PR 回写架构文档第三章；PR 标题带子阶段编号
- S2 前端：先读前置阅读中的前端章节；src/types/api.ts 由 openapi-typescript
  从后端 /openapi.json 生成、禁手改（J25），变更后重跑 pnpm gen:api 并提交生成物
- S3 测试：先读 07 对应用例节 → 指定用例全过；命中 D8 门禁条件
  （分块/清洗/检索/模型）时跑 golden 回归
- 顺序强制：S1 自检未过不进 S2；S3 不通过回退修复重跑
"""

GATE_TEMPLATE = """\
- python scripts/doc_consistency_lint.py → 0 硬错误
- mypy --strict（本单元涉及模块）→ 绿
- pytest 本单元 07 用例 → 全过
- 契约冒烟：tests/contract 四类门禁（09 §4）
- 代码/PR 描述含决策编号引用，无"重新发明论证"
"""


def extract_unit(unit_id: str) -> tuple[str, list[str]]:
    """从 01 §6 提取单元标题行与全部条目行。

    Args:
        unit_id: 单元编号（如 "1.1"）。

    Returns:
        (单元名, 条目行列表)。

    Raises:
        SystemExit: 单元不存在。
    """
    lines = DOC_01.read_text(encoding="utf-8").splitlines()
    start = None
    for i, ln in enumerate(lines):
        m = UNIT_HEADER_RE.match(ln)
        if m and m.group(1) == unit_id:
            start = i
            break
    if start is None:
        raise SystemExit(f"[fail] 单元 {unit_id} 不存在于 01 §6")
    header = UNIT_HEADER_RE.match(lines[start])
    assert header is not None
    name = header.group(2)
    body: list[str] = []
    for ln in lines[start + 1 :]:
        if UNIT_HEADER_RE.match(ln) or ln.startswith("### 6."):
            break
        if ln.strip():
            body.append(ln.lstrip("> ").strip())
    return name, body


def build_pack(unit_id: str) -> str:
    """组装派发包全文。

    Args:
        unit_id: 单元编号。

    Returns:
        派发包 Markdown 文本。
    """
    name, body = extract_unit(unit_id)
    prereads: list[str] = []
    for ln in body:
        for ref in PREREAD_RE.findall(ln):
            prereads.append(ref)
    pack = [
        f"# Agent Pack · 单元 {unit_id} · {name}",
        "",
        "## 0. 硬约束（必读，来自 AGENT.md §4）",
        HARD_CONSTRAINTS,
        f"## 1. 本单元职责（01 §6 · {unit_id}）",
        "",
    ]
    pack.extend(ln if ln.startswith("-") else f"- {ln}" for ln in body)
    pack += [
        "",
        "## 2. 前置阅读（本单元「前置阅读」引用）",
        "",
    ]
    pack.extend(f"- {ref}" for ref in dict.fromkeys(prereads))
    if not prereads:
        pack.append("- （无章节引用，按 S1/S2/S3 行内指定执行）")
    pack += [
        "",
        "## 3. 三步工作流要求（01 §6.0）",
        WORKFLOW_TEMPLATE,
        "## 4. 验收门禁（本单元必过，09 §3/§4）",
        GATE_TEMPLATE,
    ]
    return "\n".join(pack)


def main() -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="生成子阶段单元派发包（09 §1）")
    parser.add_argument("unit", help="单元编号，如 1.1")
    parser.add_argument("-o", "--out-dir", default=".", help="输出目录")
    args = parser.parse_args()
    pack = build_pack(args.unit)
    out_path = Path(args.out_dir) / f"agent-pack-{args.unit}.md"
    out_path.write_text(pack, encoding="utf-8")
    print(f"[ok] 派发包已生成: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
