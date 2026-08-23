# 08 文档一致性 Lint 规范

> **版本**: v1.0 | **日期**: 2026-08-23 | **适用对象**: 后端 / 测试 / CI
> **定位**: 把 AGENT.md「约束 6 命名同源」「约束 10 文档即事实」工程化为可在 PR 上自动跑的检查，防止 02/03/04/06/07 与架构文档之间的字段、错误码、降级枚举、ADR 编号漂移。
> **上游依据**: AGENT.md §4 约束 6/10、§6 变更同步义务速查表；实现见 `scripts/doc_consistency_lint.py`。

---

## 1. 为什么需要

文档套件以"文档为事实源"，但同步义务靠人工遵守，长期必然漂移：
- 某次改动在 07 引用了 `X-Degraded: no-persistence`，却忘了同步进 02 §2.4 枚举表；
- 在 03 引用了 `CHAT_504_TIER_TIMEOUT` 之外的新错误码，但 02 §6 总表漏登记；
- ADR 编号（如 J23）在多处引用，拼写错成 `J32` 无人发现。

Lint 把"权威源"编码成机器可校验的规则，在 CI 阻断明显违规。

## 2. 规则定义

### R1 · X-Degraded 枚举一致性（硬错误）
- **权威源**：`02_API接口契约.md` §2.4 表格列出的 `no-*` 取值。
- **检查**：扫描全部文档，出现的任何 `no-*` 降级值必须属于权威集合。
- **违规示例**：某文档写 `X-Degraded: no-<新值>`，但 02 §2.4 无此项 → FAIL。
- **修复**：先在 02 §2.4 登记该枚举（含触发条件/D5 出处），再在引用处使用。

### R2 · 错误码一致性（硬错误）
- **权威源**：`02_API接口契约.md` §6 错误码总表。
- **检查**：扫描全部文档（`02` 自身除外），引用的 `*_NNN_*` 形式错误码必须存在于总表。
- **违规示例**：03/06/07 引用了形如 `XXX_<NNN>_YYY` 但未在 02 §6 登记的新错误码 → FAIL。
- **修复**：新增错误码必须先落 02 §6 总表，并同步 06 §9 文案表（AGENT.md §6）。

### R3 · ADR 编号引用合法性（软警告，不阻断）
- **已定义集合**：架构文档 ADR 表中以 `| J23 |` 形式定义的 J/M/D/H/A/B/E 系列编号，外加管道阶段 `P1`–`P7`、图谱步骤 `G1`–`G5`（正文定义）。
- **检查**：其余文档引用的同类编号若不存在于已定义集合，发警告。
- **注意**：里程碑/联调/测试用例编号（如 `F3`、`L2`、`S-01`、`E-07`、`H-02`）与延迟指标（`P95`）已在脚本内豁免，不产生噪声。

## 3. 运行方式

```bash
# 默认扫描脚本所在目录的上一级（即文档套件根）
python scripts/doc_consistency_lint.py

# 或显式指定目录
python scripts/doc_consistency_lint.py /path/to/RAG

# CI 场景：仅关心退出码（R1/R2 违规 → 1）
python scripts/doc_consistency_lint.py . && echo "lint pass"
```

- **退出码**：存在 R1/R2 违规 → `1`；仅 R3 警告 → `0`。
- **依赖**：仅 Python 标准库（`re`/`pathlib`/`sys`），无第三方包。

## 4. CI 集成（GitHub Actions 示例）

```yaml
# .github/workflows/doc-lint.yml
name: doc-consistency
on: [pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: 文档一致性 Lint
        run: python scripts/doc_consistency_lint.py .
```

合并门禁：**R1/R2 任意违规必须修复后才能合入**（与 golden set 门禁 D8 同级，均为"文档级硬墙"）。

## 5. 与变更同步义务的对应

| AGENT.md 同步义务 | 被 Lint 覆盖的规则 |
|-------------------|--------------------|
| REST 端点/字段 → 02 + 06 types + 07 用例 | R2（错误码）、R1（降级值） |
| SSE 事件/帧语义 → 03 + 06 | R1（如新增降级信号） |
| Collection/Index/Key → 04 | （命名类，后续可扩展 R4） |
| 错误码 → 02 §6 + 06 §9 | R2 |
| 新降级信号 → 02 §2.4 | R1 |

> **后续扩展建议（R4）**：校验 04 中定义的 Collection/Redis Key 命名在 05 读写代码处的引用一致性；以及 02 §5/§7 与 06 `types/api.ts` 的字段镜像。需解析 TS 文件，暂未纳入本版。

---

*变更记录：v1.0（2026-08-23）随《RAG 开发文档套件》创建；配合 J23 降级盲区补全一并落地。*
