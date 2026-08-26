# Bug 汇总与修复计划

> **版本**: v1.0 | **日期**: 2026-08-26
> **证据基准**: 工作区实测（2026-08-26）——`mypy --strict app/core app/agent app/api`、全量 `pytest`（393 passed / 13 skipped）、前端 `typecheck`/`eslint`/`build` 三门禁、全仓 TODO/NotImplementedError 扫描、git 工作区审计。
> **关联**: 01 §6.11 单元 10.8（实现深度审计与功能补全收口）、05 §5.7（管理面端点与鉴权收口）、06 §8.2（功能补全批次）。

## 0. 摘要

> **修复进度（2026-08-26 复验）**: BUG-01 ~ BUG-11 **全部修复完毕**并已提交（cee4aa5 / c017432 / 3246687 / f07cfef / fb20209 / 0a71749）。复验门禁：mypy --strict 0 error、pytest 全量 395 passed / 13 skipped、前端 typecheck/eslint/build/vitest（16 passed）全绿、doc-lint 0 硬错误 0 软警告、git 工作区干净。本文档其余章节保留原始审计记录作为根因存档；后续新增缺陷按新增 BUG 条目追加。

本轮全量工程审计共确认 **11 项缺陷**（致命 5 / 高 3 / 中 3），全部落在「批次 A 后端收口」的收尾地带与历史遗留区。当前门禁状态：pytest 全绿、前端三门禁全绿、doc-lint 全绿，但 **mypy --strict 余 2 处错误**、**约 1450 行批次 A 改动未提交**、**1 个管理端点漏挂鉴权**。修复总原则：先堵安全面（鉴权漏网），再清类型收尾（mypy 2 处），然后一次性完成批次 A 提交卫生（删除自删失败的一次性补丁脚本、补 .gitignore），最后处置死代码桩与工程卫生项。预计总工作量约 1.5 个工作日，不涉及契约（02/03/04）变更。

## 1. 缺陷清单

### BUG-01（致命）`GET /admin/qdrant/points` 漏挂鉴权 【已修复 cee4aa5】

- **位置**: `app/api/endpoints/qdrant_debug.py:37`
- **现象**: 端点签名无 `Depends(require_admin)`，函数体内残留 `# TODO: admin 鉴权（10.2）`；且未接 `ensure_debug_enabled()` 开关。
- **根因**: 单元 10.8 批次 A 的鉴权挂载补丁（`scripts/_patch_auth.py`）目标清单为 debug/ingestion/parsing/cleaning/chunking/communities/golden/graph 八个文件，**qdrant_debug.py 不在清单内漏网**——它是 02 §3.11 调试组端点，却在批次 A 审计的「13 处」统计口径之外。
- **影响**: 任何持有有效 JWT 的普通用户（甚至无 token 时取决于 `get_qdrant_client` 依赖链）可按 doc_id 遍历全部业务集合的 points **payload 明文**（含正文 chunk、元数据），信息泄露面为 admin 级调试数据。
- **验证**: `Select-String qdrant_debug.py -Pattern require_admin` → 零命中（其余 14 个 admin 前缀路由文件均已挂载）。

### BUG-02（致命）`SemanticCache.invalidate_doc` 异常路径返回 None 破坏计数契约 【已修复 cee4aa5】

- **位置**: `app/memory/semantic_cache.py:230-231`
- **现象**: 声明 `-> int`，但 `except Exception: return`（裸 return）。
- **根因**: 该方法由 `delete_by_payload_match`（已升级为计数返回）代理而来；升级调用方时遗漏了异常分支的返回值同步——同文件 `purge_expired` 的异常分支正确写法是 `return 0`。
- **影响**: ① mypy --strict 报错（`error: Return value expected`），批次 A 门禁红，阻塞提交；② 运行时异常路径下 `admin cache/clear` 的 `purged` 计数会拿到 None 并在累加处抛 TypeError（`purged = await cache.invalidate_doc(...)` 直接赋值给 int 变量）。
- **验证**: `mypy --strict app/memory/semantic_cache.py` → 1 error。

### BUG-03（致命）`parsing_preview` 的 `raw_doc` None 收窄缺失 【已修复 cee4aa5】

- **位置**: `app/api/endpoints/parsing.py:81`
- **现象**: `raw_doc: RawDocument | None` 经 if/elif/else 三分支后，mypy 认为仍可能为 None，传入 `_router.parse(raw_doc)` 报 arg-type 错误。
- **根因**: 一次性补丁脚本对原实现做了最小侵入式类型标注（`raw_doc: RawDocument | None = RawDocument(...)`），但未重排控制流让类型收窄自然成立——elif 分支 `raw_doc = next(..., None)` 在「找到」时是 RawDocument、「未找到」时提前 raise，类型上仍是 `RawDocument | None`，mypy 无法跨分支证明非空。
- **影响**: mypy --strict 门禁红（`error: Argument 1 to "parse" ... expected "RawDocument"`）。运行时实际不可达 None（404 已提前抛出），故为类型层缺陷而非行为缺陷。
- **验证**: `mypy --strict app/api/endpoints/parsing.py` → 1 error。

### BUG-04（致命）批次 A 约 1450 行改动滞留工作区未提交 【已修复 cee4aa5】

- **位置**: git 工作区（admin/security/deps/config/qdrant_client/redis_client/semantic_cache + 11 个端点文件 + 测试 + pyproject）
- **现象**: 20 个文件已暂存/修改、`app/agent/tools.py` 已删除，但无对应提交；上一次提交停在 `fc9eecb`（10.7 BUI）。
- **根因**: 开发会话在 mypy 修复中途截断（BUG-02/03 即当时的 2 处遗留），按 01 §6.0「S1 自检未过不得进入 S2」的门禁语义，未达提交条件。
- **影响**: ① 单点丢失风险——工作区改动无版本保护；② 后续批次（B/C/D）在脏工作区上叠加会放大合并与回滚成本；③ 违反 Conventional Commits 分组提交节奏（01 §4.2）。

### BUG-05（致命）一次性补丁脚本被 `git add` 意外纳入暂存区 【已修复 cee4aa5/c017432】

- **位置**: `scripts/_patch_auth.py`、`scripts/_fix_auth_params.py`、`scripts/_fix_mypy.py`（均已 `A` 状态）
- **现象**: 三个脚本头部均注明「执行后自删」/「一次性补丁」，但因会话截断未执行删除，反而进入了暂存区。
- **根因**: 脚本设计为「补丁完自删」，但删除动作依赖会话继续执行；截断后遗留在 scripts/ 并随批量 `git add` 入暂存。
- **影响**: 一次性变异脚本入库会成为仓库长期噪音，且其「重跑即重复改写源码」的行为对后续维护者是暗雷（例如 `_patch_auth.py` 重跑会二次插入 user 参数导致语法错误）。

### BUG-06（高）`.langgraph_api/` 运行时状态文件被纳入暂存区 【已修复 c017432】

- **位置**: `.langgraph_api/`（7 个 `.pckl` 文件，均已 `A` 状态）
- **现象**: langgraph-server 本地 dev 模式的 checkpoint/store 二进制状态被 git 暂存；`.gitignore` 无对应规则。
- **根因**: `docker compose` 之外的 `langgraph dev`（或 SDK 初始化）在项目根生成该目录；`.gitignore` 编写时未预见此产物。
- **影响**: ① 二进制状态文件含会话数据（潜在 PII 面）入库；② 每次运行状态变化都会污染 `git status`，干扰真实改动的审阅。

### BUG-07（高）五个零引用 NotImplementedError 死代码桩模块（约 45 处 TODO） 【已修复 3246687】

- **位置**: `app/generation/generator.py`（StreamGenerator）、`app/generation/citation.py`（CitationTracker）、`app/pipeline/chunking/semantic_splitter.py`（SemanticSplitter）、`app/pipeline/enrichment/entity_extractor.py`（NEREntityExtractor）、`app/pipeline/enrichment/relation_enricher.py`（RelationEnricher）
- **现象**: 全仓 63 处 TODO 中的约 45 处集中于上述五个模块；每个类核心方法直接 `raise NotImplementedError`；全仓引用扫描（含 tests）**零外部引用**——实际调用链走的是 `app/agent/nodes/generator.py`（真实现，含引用/Citation 模型）、`app/pipeline/chunking/` 的真实分块器与管道自有实体抽取。
- **根因**: 阶段 0-2 早期按模块骨架先行创建的占位实现，后续真实实现落在 agent/nodes 与 pipeline 专职模块后，占位件从未清理——与批次 A 已删除的 `app/agent/tools.py`（死桩）同一性质，当时审计清单未覆盖 generation/pipeline 侧。
- **影响**: ① 约 400 行死代码 + 45 处 TODO 噪音，误导后续维护者与 AI 编码 Agent（AGENT.md 读者会以为这些是待实现任务）；② `neo4j_client.py:134` 的 TODO(阶段 3) 注释指向 04 §5.4 检索模板的说明性占位，与此同类需一并裁决。

### BUG-08（高）Qdrant 客户端版本兼容性 UserWarning 【已修复 3246687】

- **位置**: `app/db/qdrant_client.py`（客户端构造）——由 `qdrant_client/async_qdrant_remote.py:231` 发出
- **现象**: pytest 全量运行时稳定复现 `UserWarning: Failed to obtain server version. Unable to check client-server compatibility`（5 warnings 中 1 类）。
- **根因**: 测试环境 Qdrant 服务不可达（离线用例走 mock/降级路径），异步客户端构造时仍尝试拉取远端版本做兼容性检查失败。客户端构造参数未设 `check_compatibility=False`。
- **影响**: 非 failures 但属测试输出噪音；离线/降级场景（J23 语义下 Qdrant down 是明确的运行时态）下每次初始化都产生告警，可能掩盖真实 warning。
- **验证**: 全量 pytest 输出 warnings 摘要可见。

### BUG-09（中）批次 A 未决功能缺口（已登记待做，非新发现） 【已修复 fb20209/0a71749（批次 B+D）】

- **位置**: 前端 `rag-web/src/`（会话历史装载/引用角标/反馈闭环/Markdown 渲染/model 上浮/RegenerationNotice·FaithfulnessBadge）；后端 `Admin.tsx` 调试分区显隐（依赖 02 §3.7 暴露 debug_enabled）
- **现象与根因**: 见 06 §8.2 与 01 §6.11 单元 10.8 的批次 B/C 定义——会话审计已确认为「实现深度缺口」而非回归性 bug。
- **影响**: D8 bad case 回流数据源（POST /feedback）断链等；此处仅收录为修复计划的排期锚点，明细以 06 §8.2 为权威。

### BUG-10（中）`debug_enabled` 生产缺省语义与配置可见性 【已修复 f07cfef】

- **位置**: `app/core/config.py`（`debug_enabled: bool = Field(default=True, ...)`）；`.env.example` 无 `DEBUG_ENABLED` 条目；10 §2 环境变量集中表未收录
- **现象**: 调试端点组开关默认开（True），且示例环境文件未提示需显式关闭。
- **根因**: 批次 A 为保证 dev 环境调试端点可用取了宽松默认值，但「生产必须关」的约束只存在于代码注释（`SYS_403_DEBUG_DISABLED`），没有落到配置样例与运维文档——配置不可见即约束不生效（05 §6 D7 fail-fast 哲学的反面）。
- **影响**: 生产部署若照抄 `.env.example`，`/admin/debug/*` 四端点对持有 admin JWT 者默认暴露（叠加 BUG-01 则完全暴露）。

### BUG-11（中）行尾混用与提交卫生 【已修复 f07cfef（.gitattributes 归一）】

- **位置**: 仓库级——工作区改动中 `semantic_cache.py` 为 LF、其余 6 个核心文件为 CRLF；docs/ 七份文档每次 `git add` 均报「LF will be replaced by CRLF」
- **现象**: 无 `.gitattributes`，Windows 工作区 CRLF 与仓库 LF 内容混杂，git 每次触碰都产生转换告警并可能在 diff 中引入整文件行尾噪音。
- **根因**: 一次性补丁脚本用 `Set-Content -Encoding UTF8`（PowerShell 默认 CRLF）写文件，与既有 LF 文件混排；仓库从未声明行尾策略。
- **影响**: 噪音 + 潜在的虚假大 diff；对 pre-commit 钩子（01 §4）的行为也有扰动。

## 2. 最优方案探讨

**BUG-01 鉴权挂载**——备选：① 挂 `require_admin` 仅鉴权；② 挂 `require_admin` + `ensure_debug_enabled()` 双闸。**选②**：该端点属 02 §3.11 调试组，与 debug.py 四端点同组同语义；只鉴权不设开关会与同组端点的生产行为不一致（同组其余四端点均双闸）。改动两行（import + 签名），与 debug.py 现有模式逐字对齐。

**BUG-02**——备选：① 异常分支 `return 0`；② 捕获后记日志再 `return 0`。**选②**：与同文件 `purge_expired` 的「异常仅记录不抛出」注释语义对齐，且静默吞异常会复现「失效联动失败无人知晓」的可观测盲区；加 `logger.warning` 一行成本可忽略。

**BUG-03**——备选：① 调整控制流（把 doc_id 分支的 raise 提前、构造分支收窄类型）让 mypy 自然通过；② `assert raw_doc is not None`（运行时断言）；③ `cast()`。**选①**：重排为「先处理 file 分支并直接返回 → 再处理 doc_id 分支并在 None 时 404 → 兜底 400」，每个出口类型唯一，无需断言与 cast；①的代价是把 90 行函数体微调为早返回结构，但消除的是类型系统无法表达的跨分支不变量，长期最干净。②③ 都是「让类型检查器闭嘴」而非「让类型正确」。

**BUG-04/05/06 提交卫生**——备选：① 一把梭单提交全部批次 A；② 按 Conventional Commits 拆两笔：`feat(api): 单元 10.8 批次 A 管理面收口`（代码+测试+pyproject+04/05/06/07/10/01/README 文档同步）+ `chore(infra): 仓库卫生`（.gitignore/.gitattributes）。**选②**：01 §4.2 要求单一职责提交；且文档同步与代码同 PR 的惯例（05 变更记录口径）在①里会混入纯卫生噪音。三个一次性脚本与 `.langgraph_api/` 直接 `git restore --staged` + 删除，不入库。

**BUG-07 死代码**——备选：① 全部删除（与 `tools.py` 同口径）；② 保留为「未来扩展占位」。**选①**：五个模块零引用、方法体全为 NotImplementedError，且真实实现已在别处存在并经测试覆盖（393 passed 证明调用链不依赖它们）；「占位」价值为零而误导成本为正（AGENT.md 驱动的 AI Agent 会把 TODO 当待办任务）。删除前以「全仓引用扫描零命中」为硬证据，删除后跑全量回归兜底。`neo4j_client.py:134` 的注释性 TODO 改写为指向 04 §5.4 的说明注释（非死代码）。

**BUG-08**——备选：① 构造参数 `check_compatibility=False`；② 保留告警。**选①**：本项目的 Qdrant 版本策略已由 04 §1（≥1.10）+ compose `latest` 锁定，客户端侧动态兼容检查无增量价值，反而在降级场景制造噪音；一行参数即可消除。需补一条单测断言构造不产生 UserWarning。

**BUG-10**——备选：① 默认改 False + dev 用 .env 显式开；② 默认 True + .env.example/Runbook 补显式关闭指引。**选①**：安全开关的安全缺省应当是「关」——debug 端点仅 dev/联调需要，让 dev 环境付出一行配置的成本，远优于让生产承担漏配风险（fail-closed 原则，与 D7 一致）。同步动作：`.env.example` 补 `DEBUG_ENABLED=true`（dev 样例）+ 10 §2 环境变量表补行。

**BUG-11**——备选：① 全仓统一 LF（`.gitattributes` 声明 `* text=auto eol=lf` + 一次性归一化提交）；② 仅对当前脏文件转换。**选①**：仓库主体本为 LF（git 告警方向证实），一次性归一并声明策略后告警永久消失；归一化提交单独成笔（`chore(infra)`），不与功能改动混排。

## 3. 修复计划（按依赖序四批）

### 批次 R1 · 安全与门禁收尾（半天，阻塞后续全部）

| 步骤 | 动作 | 涉及 | 验证 |
|------|------|------|------|
| R1.1 | qdrant_debug.py 挂 `require_admin` + `ensure_debug_enabled()`（对齐 debug.py 模式） | BUG-01 | grep 零 TODO；补一条 401/403 契约用例 |
| R1.2 | `invalidate_doc` 异常分支改 `logger.warning(...); return 0` | BUG-02 | `mypy --strict app/memory` 绿；单测构造 Qdrant 异常断言返回 0 |
| R1.3 | `parsing_preview` 控制流重排为早返回结构 | BUG-03 | `mypy --strict app/api` 绿；既有 parsing 用例不回归 |
| R1.4 | 三门禁复跑：pytest 全量 / mypy --strict / doc-lint | — | 393+ passed、0 error、0 硬错误 |

### 批次 R2 · 提交卫生（1 小时，依赖 R1 全绿）

| 步骤 | 动作 | 涉及 |
|------|------|------|
| R2.1 | 删除 `scripts/_patch_auth.py`、`_fix_auth_params.py`、`_fix_mypy.py` 并从暂存区移除 | BUG-05 |
| R2.2 | `.gitignore` 增 `.langgraph_api/`；`git rm --cached -r .langgraph_api` | BUG-06 |
| R2.3 | 提交一：`feat(api): 单元10.8批次A管理面收口——admin真实现+14处鉴权+mypy清零(含BUG-01/02/03)`（代码+测试+pyproject+docs 同步） | BUG-04 |
| R2.4 | 提交二：`chore(infra): 仓库卫生——gitignore补langgraph运行时目录` | BUG-06 |

### 批次 R3 · 死代码与告警清理（半天，依赖 R2 干净基线）

| 步骤 | 动作 | 涉及 | 验证 |
|------|------|------|------|
| R3.1 | 删除五个零引用桩模块（generation/generator、generation/citation、pipeline/chunking/semantic_splitter、pipeline/enrichment/entity_extractor、relation_enricher） | BUG-07 | 删前全仓引用扫描零命中记录在案；删后 pytest 全量 + mypy 全量绿 |
| R3.2 | `neo4j_client.py:134` TODO 注释改写为 04 §5.4 指向说明 | BUG-07 | 全仓 TODO 降幅 ≥45 处 |
| R3.3 | Qdrant 客户端构造 `check_compatibility=False` + 告警回归单测 | BUG-08 | pytest warnings 中该类归零 |
| R3.4 | 提交：`refactor(app): 清理零引用NotImplementedError桩模块与Qdrant兼容告警` | — | — |

### 批次 R4 · 配置安全缺省与工程卫生（半天，可与 R3 并行）

| 步骤 | 动作 | 涉及 |
|------|------|------|
| R4.1 | `debug_enabled` 默认改 False；`.env.example` 补 `DEBUG_ENABLED=true`；10 §2 环境表补行；05 §5.7 与 02 §3.11 的开关表述同步 | BUG-10 |
| R4.2 | 新增 `.gitattributes`（`* text=auto eol=lf` + 二进制例外）+ 一次性行尾归一化提交 | BUG-11 |
| R4.3 | 提交：`fix(infra): debug开关改fail-closed缺省+行尾策略归一` | — |

**进度登记（2026-08-26 复验）**：批次 R1-R4 与批次 B/D 已全部执行完毕（六笔提交见 §0 摘要），验收门禁 1-5、7 已达成；门禁 6 的鉴权用例随 cee4aa5 合入。当前遗留项（均为计划内后置，非缺陷回归）：

1. **批次 C（BUI 业务包装）**：按用户定案后置，入口在 06 §8.2 / §10.4——bui/ 20 件已落地但 MessageBubble/ThoughtPanel/输入区尚未接线（引用扫描确认业务组件暂未 import bui/ 运行时件）；
2. **`Admin.tsx` 调试分区显隐**：依赖 02 §3.7 暴露 `debug_enabled` 的契约变更，属阶段 11 契约演进项，前端占位注释保留；
3. **`PostgresManifestStore`**（`app/pipeline/ingestion/manifest.py` 真实现）与 `WebLoader`（loader.py:173 网页爬取）：标注「阶段 2/3 接线」，当前 dev 装配 `JsonFileManifestStore` 为设计内降级路径（deps.py 注释明示）；
4. **`IndexUpdater` / `GraphIndexer` 桩**：graph_indexer.py 的 NotImplementedError 属阶段 3 图谱写入单元（真实写入链路在 graph_construction/graph_writer.py 且有测试覆盖），TODO 保留为阶段任务锚点；
5. **main.py lifespan 初始化 TODO（5 处）**：客户端经 deps 懒加载装配（05 §6 D7），lifespan 集中初始化属性能优化项，非功能缺陷。

## 4. 验收门禁（全部批次完成判定）

1. `pytest -q` 全量 ≥393 passed 且无新增 warning 类别；
2. `mypy --strict app/core app/agent app/api` → 0 error；
3. `python scripts/doc_consistency_lint.py . --frontend rag-web` → 0 硬错误 0 软警告；
4. `git status` 干净（无未提交实现改动、无一次性脚本、无 .langgraph_api）；
5. 全仓 TODO 扫描从 63 处降至 ≤18 处（余量属 BUI 演示数据字面量与注释性占位）；
6. 裸访 `GET /api/v1/admin/qdrant/points` 返回 401/403（新增契约用例断言）；
7. 提交历史符合 Conventional Commits 且每笔门禁绿（01 §4.2）。

---

*变更记录：v1.0（2026-08-26）创建：收录全量工程审计确认的 11 项缺陷（BUG-01~11），含根因、最优方案比选与四批次修复计划；证据基准为当日工作区实测门禁输出。v1.1（2026-08-26）修复进度登记：BUG-01~11 全部修复完毕（六笔提交：cee4aa5 R1+R2.3 / c017432 R2.4 / 3246687 R3 / f07cfef R4 / fb20209 批次B / 0a71749 批次D），复验门禁全绿（pytest 395 passed / mypy 0 error / 前端四门禁绿 / doc-lint 双零），各条目标注修复提交号；§3 新增遗留项说明（批次 C 后置、PostgresManifestStore 待阶段 2/3、Admin.tsx debug 接线待 02 §3.7）。*
