# 08 文档一致性 Lint 规范

> **版本**: v1.0 | **日期**: 2026-08-23 | **适用对象**: 后端 / 测试 / CI
> **定位**: 把 AGENT.md「约束 6 命名同源」「约束 10 文档即事实」工程化为可在 PR 上自动跑的检查，防止 02/03/04/06/07 与架构文档之间的字段、错误码、降级枚举、ADR 编号漂移；新增 BUI 设计系统依赖白/黑名单（J24）护栏。
> **上游依据**: AGENT.md §4 约束 6/10、§6 变更同步义务速查表；实现见 `scripts/doc_consistency_lint.py`。

---

## 1. 为什么需要

文档套件以"文档为事实源"，但同步义务靠人工遵守，长期必然漂移：
- 某次改动在 07 引用了 `X-Degraded: no-persistence`，却忘了同步进 02 §2.4 枚举表；
- 在 03 引用了 `CHAT_504_TIER_TIMEOUT` 之外的新错误码，但 02 §6 总表漏登记；
- ADR 编号（如 J23）在多处引用，拼写错成 `J32` 无人发现。

Lint 把"权威源"编码成机器可校验的规则，在 CI 阻断明显违规。

## 2. 规则定义

### R1 · X-Degraded 枚举一致性（硬错误，双向）
- **权威源**：`02_API接口契约.md` §2.4 表格列出的 `no-*` 取值。
- **正向检查**：扫描全部文档，出现的任何 `no-*` 降级值必须属于权威集合。
  - **违规示例**：某文档写 `X-Degraded: no-<新值>`，但 02 §2.4 无此项 → FAIL。
  - **修复**：先在 02 §2.4 登记该枚举（含触发条件/D5 出处），再在引用处使用。
- **反向检查（防漏）**：`06_前端开发指南.md` §9 的 `X-Degraded` Banner 文案表必须**覆盖 02 §2.4 全部取值**；权威源新增取值而 06 未同步 → FAIL。
  - **违规示例**：02 §2.4 含 `no-persistence`，但 06 §9 未列 → FAIL（本类漂移 08 v1 单向检查曾漏检，见 §1）。
  - **修复**：在 06 §9 补该取值的 Banner 文案，并与 02 同 PR 更新。

### R2 · 错误码一致性（硬错误）
- **权威源**：`02_API接口契约.md` §6 错误码总表。
- **检查**：扫描全部文档（`02` 自身除外），引用的 `*_NNN_*` 形式错误码必须存在于总表。
- **违规示例**：03/06/07 引用了形如 `XXX_<NNN>_YYY` 但未在 02 §6 登记的新错误码 → FAIL。
- **修复**：新增错误码必须先落 02 §6 总表，并同步 06 §9 文案表（AGENT.md §6）。

### R3 · ADR 编号引用合法性（软警告，不阻断）
- **已定义集合**：架构文档 ADR 表中以 `| J23 |` 形式定义的 J/M/D/H/A/B/E 系列编号，外加管道阶段 `P1`–`P7`、图谱步骤 `G1`–`G5`（正文定义）。
- **检查**：其余文档引用的同类编号若不存在于已定义集合，发警告。
- **注意**：里程碑/联调/测试用例编号（如 `F3`、`L2`、`S-01`、`E-07`、`H-02`）与延迟指标（`P95`）已在脚本内豁免，不产生噪声。

### R4 · BUI 设计系统依赖白/黑名单（J24）（硬错误）
- **权威源**：`06_前端开发指南.md` §10.2 依赖替换规则 + `前端设计系统落地方案.md`。
- **检查对象**：前端源码 `rag-web/src/components/bui/**`（实现需扩展 `scripts/doc_consistency_lint.py` 以扫描该目录，与文档扫描分轨）。
- **禁止项（命中即 FAIL）**：
  - banned 依赖导入：`@central-icons-react`、`iconoir-react`、`posthog-js`、`glimm`、`liveline`、`@/components/primitives/GlideMenu`、`@/components/atoms/Button`、`@/components/atoms/Shimmer`、`@/components/atoms/StreamText`；
  - 硬编码颜色：除 `color-mix(...)` 调色与 `dark:` 变体外，`bui/` 内出现 `#xxxxxx` / `rgb(...)` / `hsl(...)` 字面量；
  - 图标未统一 `lucide-react`，或令牌（颜色/阴影/圆角）未仅经 `src/styles/globals.css`。
- **违规示例**：`bui/sidebar-nav.tsx` 残留 `import … from "@central-icons-react/…"` → FAIL；`bui/foo.tsx` 写 `bg-[#1a1a1a]` → FAIL。
- **修复**：按 06 §10.2 替换依赖（lucide-react / shadcn Popover / recharts / 本地原子）；颜色改引用 `globals.css` 令牌。
 - **退出码**：命中 → `1`（与 R1/R2 同列硬墙）。

### R5 · 代码↔文档契约一致性（硬错误，代码阶段生效）
- **权威源**：02 §3.6 端点 + §5 类型字段（机器真源为后端 `/openapi.json`）、03 §3.3/§3.4 SSE 事件/字段、04 存储 Key/Collection/Index。
- **检查**：扩展本脚本扫描后端代码（`app/core/models.py`、`app/api/**`、`app/store/**` 等），断言 ① FastAPI 路由/方法 ⊆ 02 §3.6；② Pydantic 模型字段 ⊆ 02 §5；③ SSE 发送事件名/字段 ⊆ 03 §3.3/§3.4；④ 存储 Key/Collection/Index 命名 ⊆ 04。同时校验前端 `types/api.ts` 为生成物（与 06 §2、J25 一致），无手改痕迹。
- **违规示例**：后端新增路由未登记 02、或 `types/api.ts` 与 `/openapi.json` 不符（未重跑 `pnpm gen:api`）→ FAIL。
- **修复**：先在权威文档登记（走文档修正 PR），再改代码；或重跑 `pnpm gen:api` 提交生成物。
- **退出码**：命中 → `1`。

### R6 · 决策编号引用合规性（硬错误，代码阶段生效）
- **已定义集合**：同 R3（架构 ADR 表 + 管道阶段 `P1`–`P7` + 图谱步骤 `G1`–`G5`）。
- **检查**：扫描代码注释与 PR 标题/提交信息中出现的 `[JMDHABEGP]\d+`，若不存在于已定义集合 → FAIL；同时校验 PR 标题符合 Conventional Commits（scope 与子阶段单元 `x.y` 对应）。
- **违规示例**：代码注释写 `按 J99 设计` 但无此 ADR；PR 标题缺 scope → FAIL。
  - **修复**：补登 ADR（文档修正 PR）或修正引用；PR 标题补 scope。
  - **退出码**：命中 → `1`。

### R7 · 02 §7 ↔ 前端 `types/api.ts` 枚举/类型镜像（硬错误，需 `--frontend`）
- **权威源**：`02_API接口契约.md` §7 TypeScript 类型对照（含 `AgentNodeName` / `DegradedReason` 等枚举与 `Citation` / `AssistantMessage` 等接口）。
- **检查**：以 `--frontend <rag-web>` 指向源码，解析 `src/types/api.ts`，断言 02 §7 导出的 interface/type 名称（双向）均在前端出现；文档有而前端缺，或前端私加未登记类型 → FAIL。
- **前提**：未提供 `--frontend` 时软跳过（警告），保证仅跑文档仓库的 CI 不受影响。
- **范围**：本期仅类型名级；字段级为后续增强（避免引入 TS AST 解析，保持标准库依赖）。

### R8 · `AgentNodeName` ↔ 前端 `summarize()` 覆盖（硬错误，需 `--frontend`）
- **权威源**：02 §7 的 `AgentNodeName` 联合类型（图节点枚举，03 §3.3/§3.4）。
- **检查**：比对前端 `src/hooks/useChatStream.ts`（或提取后的 `src/lib/summarize.ts`）中 `summarize()` 处理的节点分支（`case "..."` / `summarize("...")`），确保每个 `AgentNodeName` 成员都有对应分支；遗漏 → FAIL。
- **前提**：同 R7，需 `--frontend`；未提供则软跳过。

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
| REST 端点/字段 → 02 + 06 types + 07 用例 | R2（错误码）、R1（降级值）、R5（代码↔文档字段/路由） |
| SSE 事件/帧语义 → 03 + 06 | R1（如新增降级信号）、R5（SSE 事件/字段） |
| Collection/Index/Key → 04 | R5（代码↔文档命名/字段校验） |
| 错误码 → 02 §6 + 06 §9 | R2 |
| 新降级信号 → 02 §2.4 | R1 |
| 前端类型镜像（02 §7 ↔ types/api.ts） | R7 |
| Agent 节点枚举（AgentNodeName ↔ summarize） | R8 |
| BUI 设计系统依赖/令牌 → 06 §10.2 + 前端设计系统落地方案.md（J24） | R4 |
| 后端契约单源 / TS 代码生成（J25） | R5（types/api.ts 生成物校验） |
| 代码/PR 引用 ADR 编号、提交规范 | R6 |

> **后续扩展建议（R7）**：在 R5 基础上进一步校验 04 中定义的 Collection/Redis Key 命名在 05 读写代码处的实际引用位置（需解析 Python AST），形成"命名被使用"的正向证明。R5/R6 已覆盖 02 §5/§7 与 `types/api.ts` 的字段镜像及 ADR 编号合规，本项为其纵深补强。

---

*变更记录：v1.0（2026-08-23）随《RAG 开发文档套件》创建；配合 J23 降级盲区补全一并落地。v1.1 新增 R4（BUI 设计系统依赖白/黑名单，J24）硬墙规则，并在 01 §6.11 注册 10.7 子阶段、AGENT.md 硬约束 #11 同步。v1.2 规划新增 R5（代码↔文档契约一致性，含 `types/api.ts` 生成物校验）与 R6（决策编号引用/提交规范），配合 J25 强联调治理；具体扫描实现留代码阶段。*
