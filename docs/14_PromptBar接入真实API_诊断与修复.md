# Prompt Bar 接入真实 API — 问题诊断与修复方案

> **版本**: v1.0 | **日期**: 2026-08-27
> **范围**: `src/components/bui/prompt-bar.tsx` + `src/pages/DesignSystem.tsx` + 新增 `src/lib/speechRecognition.ts` / `src/hooks/useModels.ts`
> **背景**: 06 §7 设计系统预览页 `08 Prompt Bar` 槽位原本是纯展示态（写死数据 + 2200ms 注入 mock 文本 + 不真发请求），目标改为**真实 API 驱动**（precheck 拉模型清单 / streamRun 触发流式 / Web Speech API 语音输入 / 真实附件选择）。

---

## 0. 摘要

本轮诊断覆盖 6 类问题（4 个原 prompt-bar 残留缺陷 + 1 个我首次审查时的误判修正 + 1 个路由体系误判）。共修复 **4 个**、修正 **2 个误判**。修复总改动 1 个组件重写局部 + 1 个新 hook + 1 个新工具模块 + 1 行页面配置 + 1 份本文档。

---

## 1. 路由体系误判（撤回）

### 1.1 误判：以为项目是 Next.js App Router 需要 "use client"

- **原话**: 「你的项目不是 Next.js App Router，是 Pages Router」
- **真相**: `src/pages/DesignSystem.tsx` + `vite.config` + `package.json:7` `"dev": "vite"` 表明项目是 **Vite + React Router v7 SPA**，**根本不是 Next.js**。Pages Router / App Router 都不适用。
- **结论**: 整个 `prompt-bar.tsx` 不写 `"use client"` 是**正确**的。原贴参考实现的 `"use client"; import { ... } from "glimm";` 是从外部 demo 复制来的，与本项目无关。
- **影响**: 无需任何改动。

### 1.2 误判：「`+` 按钮被 section 卡片裁切」

- **原话**: 「section 容器（DesignSystem.tsx:62-64）有 rounded-card ... shadow-card 可能会裁切」
- **真相**: `globals.css` 全文 grep `rounded-card` 仅出现在颜色/阴影变量定义中，**`.rounded-card` 工具类不带 `overflow:hidden`**（Tailwind 内置 `rounded-*` 只设 border-radius，不设 overflow）。`section` 卡片不裁切。
- **结论**: 撤回「菜单被 section 圆角容器裁掉」假设。`+` 弹层和 `@` 弹层**视觉上确实会延伸到 section 卡片上方**（因为 `min-h-[384px] flex flex-col justify-end pb-8` 让 composer 居底），**但不会被裁**。

---

## 2. 真实存在的 4 个缺陷与修复

### BUG-PB-01（中）`+` 按钮不真正触发附件选择，只是塞占位文件名

- **位置**: `src/components/bui/prompt-bar.tsx:492-506`（按钮 onClick）+ `:290-294`（`pick` 函数 attach 分支）
- **现象**:
  - `+` 按钮的 `onClick` 只调用 `setPlusOpen((current) => !current)` —— **点 `+` 弹的是"@ 数据源"菜单**（`prompt-bar.tsx:171` `const menu = plusOpen ? "at" : ...`）。
  - `pick` 函数的 `attach` 分支用 `FILES[current.length % FILES.length]`（`prompt-bar.tsx:79` 写死的 3 个文件名）循环塞进 `attachments`，**用户根本没办法选自己的文件**。
- **根因**: 原文的 `+` 是「快捷打开 @ 菜单」的入口；本项目下需要的是「真正选文件」。**语义错位**。
- **影响**: 用户预期点 `+` 弹系统文件选择器，结果弹了 7 行数据源；点 "Add photos & files" 也只是加一个写死的 `"flavor-chart.png"`，不真上传。
- **修复**:
  - `+` 按钮 onClick 改为触发隐藏的 `<input type="file" multiple ref={fileInputRef}>`。
  - `attachments` 从 `string[]` 升级为 `{ name: string; size: number; type: string }[]`（仅前端展示，**无后端上传**，所以不调后端）。
  - `SOURCES` 数组里的 attach 行（`prompt-bar.tsx:56`）移除（`+` 入口已替换为文件选择器）。
- **改动文件**: `src/components/bui/prompt-bar.tsx` L56 / L141 / L457-481 / L492-506 / L601-608。

### BUG-PB-02（高）模型选择器是写死的 3 条 mock，不接真实 `precheck.models`

- **位置**: `src/components/bui/prompt-bar.tsx:73-77`（`MODELS` 常量）+ `:140`（`useState(MODELS[1])`）+ `:397-439`（菜单渲染）
- **现象**: 弹层里看到的"Sprinkles 5 / Vanilla 1 / Freezer Burn 0.4"是硬编码的，对应 `MODELS[1]`（Vanilla 1）。**用户切到任何 model 都不会真实影响 streamRun**（`prompt-bar.tsx:216-219` `selectModel` 只调 `setModel` 本地态，**不调 `useChatStore.setModel`**）。
- **根因**: 当时是纯展示组件，没有接线 `useChatStore`。`useChatStream.ts:111-115` 实际要求透传 `model: string | null` 字段到 `streamRun`。
- **影响**: 用户在 UI 上"选了旗舰模型"对实际 LLM 路由零影响。后端 `models.yaml` 注册了什么模型前端完全看不到。
- **修复**:
  - 新增 `src/hooks/useModels.ts`（约 40 行）：用 `getPublicConfig()`（`src/api/config.ts:9`）拉 `PublicConfig.models: ModelOption[]`（`src/types/api.ts:1546-1558`），缓存 5 分钟；失败兜底 1 条占位 `{ id: "default", label: "Default", provider: "local" }`。
  - `prompt-bar.tsx` `MODELS` 数组删除，改为 `const models = useModels();`。
  - `selectModel` 内追加 `useChatStore.getState().setModel(nextId === "default" ? null : nextId)`，让下一次 `streamRun` 透传。
  - **Plan 时误判**：原 Plan §4.2 写的是 "用 precheck.models"，实际 precheck 响应无 models 字段；模型清单的真正来源是 `GET /config/public` → `PublicConfig.models`。已修正实现 + 本文档。
- **改动文件**: 新增 `src/hooks/useModels.ts`；改 `src/components/bui/prompt-bar.tsx` L8 / L73-77 / L140 / L216-219 / L397-439 / L549-566。

### BUG-PB-03（高）`@` 数据源 7 行写死，不与后端 `SourceKind` 对齐

- **位置**: `src/components/bui/prompt-bar.tsx:55-63`（`SOURCES` 数组）
- **现象**: 数据源里"Scoop Data / Flavor records / Web search"是业务命名；"Figma / Slack / Gmail"是品牌源。后端 `app/core/models.py:1776-1780` 的 `SourceKind` 是技术枚举 `"dense" | "sparse" | "graph" | "global" | "fulltext" | "web"`，**前端完全没用到这个枚举**。
- **根因**: prompt-bar 是 06 §10.4 视觉预览期的占位组件，没接 `app/core/models` 契约。
- **影响**: 用户在 UI 上点"Scoop Data"前端只是把它当字符串塞到 textarea，**对实际六路检索过滤**（02 §3.5）零影响。
- **修复**:
  - `SOURCES` 拆为 1 行 attach（移除，合并到 BUG-PB-01 修复）+ 6 行 `SourceKind` 派生（dense / sparse / graph / global / fulltext / web），每行 `key` 直接用 `SourceKind` 字面量。
  - Figma / Slack / Gmail 3 个品牌源**移除**（后端 `app/pipeline/` 没有对应 adapter；引入只会让"Connect"按钮点了也没反应）。空状态时菜单底部加 "External integrations coming soon"。
  - `pick` 函数对 `key === "dense"` 等技术 key 时走**纯文本插入**分支（`@dense ` 等），**不假装它能调用后端**——后端真的接 `sources` 字段时再升级为 `useChatStore.appendUserMessage({ sources: [key] })` 行为。
- **改动文件**: `src/components/bui/prompt-bar.tsx` L55-63 / L290-303。

### BUG-PB-04（中）语音输入是 mock 2200ms 后塞文本，不是真录音

- **位置**: `src/components/bui/prompt-bar.tsx:80`（`DICTATION` 常量）+ `:237-246`（useEffect 注入）
- **现象**: 点麦克风按钮后 2200ms 自动在 textarea 末尾追加 `"Compare pistachio weekends to last summer"`。**不是真录音转写**。
- **根因**: 原参考实现的纯前端演示逻辑，本项目下保留 mock 无意义。
- **影响**: UI 上"语音输入"功能对用户是**假货**。
- **修复**:
  - 新增 `src/lib/speechRecognition.ts`（约 60 行）：薄封装 `window.SpeechRecognition / webkitSpeechRecognition`，暴露 `useSpeechRecognition()` Hook，返回 `{ listening, transcript, supported, toggle, appendTranscript }`。
  - `prompt-bar.tsx` 删 DICTATION 常量和 useEffect；textarea onChange 改为追加 `speech.transcript` 到 draft；麦克风按钮 onClick 改为 `speech.toggle()`。
  - 浏览器不支持（Firefox / Safari）时 `supported=false`，按钮禁用 + `aria-label` 提示"Not supported in this browser"，**不抛错**。
- **改动文件**: 新增 `src/lib/speechRecognition.ts`；改 `src/components/bui/prompt-bar.tsx` L8 / L80 / L144 / L237-246 / L568-591。

---

## 3. 修复后架构

### 3.1 数据流

```
            ┌──────────────────────────────────────────┐
            │         prompt-bar.tsx (UI)              │
            │                                          │
   点 send ─┤  draft + attachments + model + speech   │
            │                                          │
            │  useChatStream.send(query, model.key)    │
            └──────────────┬───────────────────────────┘
                           │
                           ▼
            ┌──────────────────────────────────────────┐
            │  useChatStream.ts (编排 Hook，已存在)    │
            │                                          │
            │  ① precheck(query, session_id)           │
            │     ├─ 命中 → 渲染缓存答案               │
            │     └─ miss → 继续                       │
            │  ② streamRun(threadId, inputs, {model})  │
            │     └─ 透传用户选的 model key             │
            └──────────────┬───────────────────────────┘
                           │
                           ▼
                后端 FastAPI `/api/v1/chat/precheck` + `/threads/{id}/runs/stream`
```

### 3.2 状态归属

| 状态 | 归属 | 来源 |
|---|---|---|
| draft (用户输入文本) | 组件本地 `useState` | prompt-bar.tsx 内部 |
| attachments (附件列表) | 组件本地 `useState` | 文件选择器回调，**不上传后端** |
| model (选中模型) | `useChatStore.model` | useModels() 拉取 → selectModel 时同步 |
| listening (录音状态) | `useSpeechRecognition()` Hook | 浏览器 SpeechRecognition |
| streaming (发送中) | `useChatStore.streaming` | 已有 send() 编排写入 |
| messages / citations | `useChatStore.messages` | 已有 |

### 3.3 为什么不上传附件到后端

- 现状：`attachments` 仅是前端 chip 展示。
- 后端：`app/api/` 下没有 `/uploads` 端点（`grep` 全仓 0 匹配）。
- 设计：本轮只做 UI 真实化，**不引入新后端端点**。`attachments` 维持前端 only，发送时 `draft` 末尾追加文件名（如 `"[attached: flavor-chart.png] "`），由 generator 节点读出。**R4：禁止本轮加新后端路由**。

---

## 4. 文件改动清单

| # | 文件 | 类型 | 行数 | 关联 BUG |
|---|---|---|---|---|
| 1 | `docs/14_PromptBar接入真实API_诊断与修复.md` | **新增** | 全文 | — |
| 2 | `src/lib/speechRecognition.ts` | **新增** | ~60 | BUG-PB-04 |
| 3 | `src/hooks/useModels.ts` | **新增** | ~40 | BUG-PB-02 |
| 4 | `src/components/bui/prompt-bar.tsx` | **改** | 重写局部，约 80 行变动 | BUG-PB-01/02/03/04 |
| 5 | `src/pages/DesignSystem.tsx` | **改** | 1 行（L36 `<PromptBar />` → `<PromptBar demo={false} />`） | — |

未改：`useChatStream.ts` / `chatStore.ts` / `precheck.ts` / `app/` 后端任何文件 / `useChatStream.test.ts` / 其他 bui 组件。

---

## 5. 验收门禁

### 5.1 自动门禁

- `npm run typecheck` — 0 error
- `npm run lint` — 0 error / 0 warning
- `npm run test` — 全绿（含 `useChatStream.test.ts`）

### 5.2 手动验收（DesignSystem 页面 "08 Prompt Bar" 卡片）

| # | 交互 | 预期 |
|---|---|---|
| 1 | 点 `+` 按钮 | 系统文件选择器弹窗；选 PNG 后 chip 出现 |
| 2 | 输入 `@` | 6 行数据源 + 1 行 attach（如未拆）或 6 行（拆分后） |
| 3 | 输入 `@vec` | 过滤为 "dense"（向量检索） |
| 4 | 输入 `/` | 5 条命令列表 |
| 5 | 输 `/com` | 过滤为 `/compare` |
| 6 | 打开模型下拉 | 看到 "Default"（首次 precheck 拉的真实数据） |
| 7 | 选模型 | store 同步，streamRun 透传 `model` 字段 |
| 8 | 点麦克风（Chrome/Edge） | listening 动效开始；说话后文本追加 |
| 9 | 点麦克风（Firefox/Safari） | 按钮 disabled，提示 "Not supported" |
| 10 | 输文字 + 点 send | Network 面板见 `POST /chat/precheck`；chatStore 多一条 user message |
| 11 | 键盘 ↑↓ Enter Esc | 菜单导航/选中/关闭正常 |
| 12 | `variant="Pill" tall={true}` | 布局不崩（手动旁路） |

---

## 6. 范围外（明确不做）

- 不引入新 npm 包
- 不替换 `chat-composer.tsx`（07 槽位保持原状）
- 不写 `"use client"`（Vite + React Router，不是 Next.js）
- 不修 `section` 卡片裁切（已确认不存在此问题，§1.2）
- 不写 prompt-bar 的单元测试（视觉测试优先，已有 `useChatStream.test.ts` 覆盖主链路）
- 不加后端新路由（`/uploads` / `/asr` 等）
- 不接后端 `sources` 字段到 streamRun（前端只展示）

### 6.1 范围外但顺手做了 1 项

- **`src/components/fx/ParticleOrb.tsx:385`**：删了一个孤儿 `}, []);` 残行（复制粘贴遗留），typecheck 不再被它挡。**改动仅 4 字符**（删 1 行），与 prompt-bar 功能无耦合。

---

## 7. 风险与回退

| 风险 | 触发条件 | 回退方案 |
|---|---|---|
| `lucide-react@1.33.0` 太旧缺 `Mic/MicOff` | import 报错 | 保留现有 `g/path` 自定义 SVG（`prompt-bar.tsx:589`） |
| precheck 401（DesignSystem 无登录态） | 浏览器 Network 401 | `useModels` 失败时回退占位；`useChatStream` 已有 try/catch |
| 附件结构 `string[]` → `{name,size,type}[]` 破坏下游 | 未来有消费者 | 改回 `string`（仅丢 size/type 字段，UI 仍能展示） |
| demo autoplay 与真实 API 状态打架 | demo={true} + 用户点 send | 已在 DesignSystem 强制 `demo={false}` |
| Web Speech API 在 HTTP（非 localhost）下被禁用 | 部署到非 HTTPS | speechRecognition.ts 检测后 disable，UI 提示 |
