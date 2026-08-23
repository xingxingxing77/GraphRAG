# 02 API 接口契约

> **版本**: v1.0 | **日期**: 2026-08-23 | **适用对象**: 后端 / 前端
> **权威声明**: 本文件是全部 HTTP 接口的**唯一权威定义源**。前端按此开发（配合 06），后端按此实现（配合 05）；其余文档只引用不重复定义。冲突时以本文件为准并回写架构文档。
> **上游依据**: 架构文档 §3.6 REST 规范、§2.2 双服务时序；决策编号沿用其速查表。

> **机器契约声明（J25）**：后端 FastAPI 导出的 `/openapi.json` 是所有接口字段、请求/响应模型、错误体的**机器真源**；本文是人读镜像。二者冲突以 OpenAPI 为准并回写本文（文档修正 PR 走 AGENT.md §4.10）。前端 `types/api.ts` 由 `openapi-typescript` 从 `/openapi.json` 生成、禁手改（见 06 §2、09 §4）。

---

## 1. 双服务边界总览

```
浏览器
  ├── REST(JSON) ──────► FastAPI 业务面  :8000   认证/会话/反馈/图谱代理/配置/缓存短路/健康/admin
  └── SDK(SSE)   ──────► langgraph-server :8001  聊天主链路 (/threads · /runs · stream)
```

| 服务 | 端口 | 职责 | 鉴权 |
|------|------|------|------|
| FastAPI 业务面 | 8000 | 非流式数据服务（J19 收缩后职责） | JWT（用户态）+ X-API-Key（服务态） |
| langgraph-server | 8001 | Agent 全链路图托管（J19） | custom auth 校验与业务面同源的 JWT |

## 2. 通用约定

### 2.1 Base URL 与协议

- 业务面：`http://<host>:8000/api/v1`（以下示例省略前缀写作 `POST /auth/token`）
- Agent 面：`http://<host>:8001`（LangGraph Server 标准 API，路径不带版本号）
- 全部 JSON（`Content-Type: application/json`）；时间一律 ISO 8601 UTC（`2026-08-23T08:30:00Z`）

### 2.2 认证（J16）

**获取 Token**：见 §3.1 `POST /auth/token`。

**携带方式**：

| 方式 | 头格式 | 场景 |
|------|--------|------|
| JWT | `Authorization: Bearer <token>` | 所有用户态端点 |
| API Key | `X-API-Key: <key>` | 仅 `/auth/token` 兑换与服务间调用 |

**JWT 结构**（HS256，密钥 `JWT_SECRET` 双服务共享）：

```json
{
  "sub": "u_9f8a7b6c",          // user_id
  "role": "user",               // "user" | "admin"
  "iat": 1755930000,
  "exp": 1756016400,            // 有效期 24h；过期重走 /auth/token 兑换（v1 无 refresh token）
  "iss": "rag-app"
}
```

### 2.3 统一错误体与状态码

所有非 2xx 响应：

```json
{ "code": "CHAT_400_INVALID_TIER", "message": "latency_tier 取值非法", "detail": {"allowed": ["fast","standard","deep"]} }
```

| 状态码 | 语义 | 错误码前缀 |
|--------|------|-----------|
| 400 | 参数校验失败 | `AUTH_/CHAT_/GRAPH_/SYS_` + `_400_` |
| 401 | 未认证 / Token 无效或过期 | `AUTH_401_*` |
| 403 | 已认证但无权限（如普通用户访问 /admin） | `AUTH_403_*` |
| 404 | 资源不存在 | `*_404_*` |
| 429 | 限流触发 | `*_429_RATE_LIMITED` |
| 500 | 内部错误 | `SYS_500_INTERNAL` |
| 503 | 依赖不可用（降级运行中） | `SYS_503_*` |
| 504 | 上游超时 | `*_504_*` |

完整错误码清单见 §6。

### 2.4 降级透传头 `X-Degraded`

任何经历了降级路径的响应携带该头（多值逗号分隔）：

| 取值 | 触发条件（对应架构 D5） |
|------|--------------------------|
| `no-graph` | Neo4j 不可用，跳过 graph/fulltext/global 三路 |
| `no-rerank` | Reranker 故障/超时，退化为粗排 Top-K |
| `llm-fallback` | 主生成模型失败，fallback 至轻量模型 |
| `no-memory` | Redis 不可用，记忆读写跳过 |
| `no-cache` | Qdrant/Redis 缓存层不可用，precheck 按 miss 处理（缓存永不阻塞主链路，J22） |
| `budget-exhausted` | wall-clock/token 预算耗尽强制降级作答（B4） | 同 B4 |
| `no-persistence` | Postgres/checkpoint 不可用，Agent 以内存态 ephemeral store 临时运行，答案仍返回但不落库（J23） | 会话历史/多轮状态无法保存，前端顶栏提示"对话未保存" |

SSE 流内等价信号见 03 §5。

### 2.5 游标分页

- 请求：`GET ...?cursor=<opaque>&limit=<int≤100>`（limit 默认 20）
- 响应体固定含 `next_cursor: string | null`；null 表示无更多页

## 3. FastAPI 业务面端点详设

### 3.1 POST /auth/token —— 签发 JWT

| 项 | 值 |
|----|-----|
| 鉴权 | X-API-Key（服务兑换）或用户凭证 |
| 用途 | 登录凭证交换（J16） |

**请求体**（二选一）：
```json
// 方式 A：API Key 兑换（服务账号）
{ "grant_type": "api_key", "api_key": "ak-xxxx" }
// 方式 B：用户凭证
{ "grant_type": "password", "username": "alice", "password": "***" }
```

**响应 200**：
```json
{ "access_token": "eyJhbGciOi...", "token_type": "bearer", "expires_in": 86400, "user": {"id": "u_9f8a7b6c", "name": "alice", "role": "user"} }
```

**错误码**：`AUTH_400_BAD_CREDENTIALS`（凭证错误）、`AUTH_401_INVALID_API_KEY`、`AUTH_429_RATE_LIMITED`（兑换限流更严）

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "X-API-Key: ak-xxxx" -H "Content-Type: application/json" \
  -d '{"grant_type":"api_key","api_key":"ak-xxxx"}'
```

### 3.2 GET /sessions —— 当前用户会话列表

| 项 | 值 |
|----|-----|
| 鉴权 | JWT |

**Query**：`cursor`, `limit`

**响应 200**：
```json
{
  "items": [
    { "session_id": "s_a1b2c3", "title": "清蒸鲈鱼怎么做？", "message_count": 6,
      "created_at": "2026-08-23T02:00:00Z", "updated_at": "2026-08-23T02:10:00Z" }
  ],
  "next_cursor": null
}
```
`title` 为该会话首条用户消息截断（≤30 字符）。

### 3.3 GET /sessions/{id}/messages —— 会话历史消息

| 项 | 值 |
|----|-----|
| 鉴权 | JWT（仅本人会话，他人返回 404） |
| 数据源 | thread checkpoint（J21）聚合工作记忆窗口 |

**Query**：`cursor`, `limit`（默认 50）

**响应 200**：
```json
{
  "items": [
    { "message_id": "m_001", "role": "user", "content": "清蒸鲈鱼怎么做？", "created_at": "...Z" },
    { "message_id": "m_002", "role": "assistant", "content": "**清蒸鲈鱼**步骤如下…[1]",
      "citations": [ { "marker": 1, "result_ids": ["r_88"], "quote": "大火蒸 8 分钟" } ],
      "degraded": false, "latency_tier": "standard", "model": "deepseek-chat",
      "created_at": "...Z" }
  ],
  "next_cursor": null
}
```

**错误码**：`SESSION_404_NOT_FOUND`

### 3.4 DELETE /sessions/{id} —— 删除会话及其记忆

| 项 | 值 |
|----|-----|
| 鉴权 | JWT（仅本人） |
| 行为 | 删除 thread checkpoint + 工作记忆 List + 该 session 的情景记忆 points（异步） |

**响应**：`204 No Content`　**错误码**：`SESSION_404_NOT_FOUND`

### 3.5 POST /feedback —— 点赞/点踩上报

| 项 | 值 |
|----|-----|
| 鉴权 | JWT |
| 用途 | 在线评估闭环数据源（架构第九章） |

**请求体**：
```json
{ "session_id": "s_a1b2c3", "message_id": "m_002", "rating": "down",
  "reason": "wrong", "comment": "蒸制时间与来源不符" }
```
`rating ∈ up | down`；`reason ∈ wrong | incomplete | unsafe | other`（仅 down 必填）。

**响应 200**：`{ "ok": true }`　**错误码**：`FEEDBACK_404_MESSAGE_NOT_FOUND`

> 约定：`rating=down` 的记录自动进入 bad case 回流队列，供 golden set 维护者筛选（D8 来源③）。

### 3.6 GET /graph/subgraph —— 图谱子图代理

| 项 | 值 |
|----|-----|
| 鉴权 | JWT |
| Query | `entity`（必填，规范实体名）、`depth`（默认 2，上限 3）、`limit`（默认 50，上限 200） |

**响应 200**（@neo4j-nvl/react 直接可用格式）：
```json
{
  "nodes": [
    { "id": "e_dish_qzy", "label": "清蒸鲈鱼", "type": "Dish", "zone": "core" },
    { "id": "i_luyu", "label": "鲈鱼", "type": "Ingredient", "zone": "core" }
  ],
  "relationships": [
    { "source": "e_dish_qzy", "target": "i_luyu", "type": "REQUIRES" }
  ]
}
```
`zone ∈ core | open`（J12 白名单/开放区）。**安全约束：bolt 地址与数据库凭证严禁出现在响应或前端代码中。**

**错误码**：`GRAPH_404_ENTITY_NOT_FOUND`、`GRAPH_503_STORE_UNAVAILABLE`（Neo4j 不可用，响应头含 `X-Degraded: no-graph`）

### 3.7 GET /config/public —— 公共配置下发

| 项 | 值 |
|----|-----|
| 鉴权 | JWT |
| 用途 | J2「请求参数指定模型」的前端前提 |

**响应 200**：
```json
{
  "models": [
    { "id": "deepseek-chat", "label": "DeepSeek Chat", "provider": "cloud" },
    { "id": "gpt-main", "label": "GPT-4o", "provider": "cloud" },
    { "id": "local-qwen32b", "label": "Qwen2.5-32B（本地）", "provider": "local" }
  ],
  "latency_tiers": ["fast", "standard", "deep"],
  "compression_strategies": ["llm_extract", "extractive", "none"],
  "profile": "cloud-primary"
}
```

### 3.8 POST /chat/precheck —— L1 语义缓存短路查询（J22）

| 项 | 值 |
|----|-----|
| 鉴权 | JWT |
| 语义 | 查询向量 ANN 检索 Qdrant cache collection，score ≥0.95 命中（H2） |

**请求体**：
```json
{ "query": "今日天气怎么样", "session_id": "s_a1b2c3" }
```

**命中响应 200**：
```json
{ "hit": true, "answer": "……", "citations": [], "cache_score": 0.97, "matched_query": "今天天气如何" }
```

**未命中响应 200**：
```json
{ "hit": false, "suggested_run": { "latency_tier": "standard" } }
```
`suggested_run.latency_tier` 由意图分类的轻量启发式给出（仅建议，前端可覆盖）。

**错误码**：`CHAT_400_EMPTY_QUERY`；Redis/Qdrant 异常时不报错——返回 `{hit:false}` 并置 `X-Degraded: no-cache`（缓存永不阻塞主链路）。

### 3.9 GET /health 与 GET /ready —— 健康聚合

| 端点 | 鉴权 | 语义 |
|------|------|------|
| `GET /health` | 公开 | 进程存活（liveness） |
| `GET /ready` | 公开 | 下游依赖聚合就绪（readiness），任一 critical 依赖 down 则 503 |

**响应 200（/ready）**：
```json
{
  "status": "ready",
  "components": {
    "postgres":         { "status": "up", "latency_ms": 3 },
    "qdrant":           { "status": "up", "latency_ms": 5 },
    "neo4j":            { "status": "up", "latency_ms": 12 },
    "elasticsearch":    { "status": "up", "latency_ms": 8 },
    "redis":            { "status": "degraded", "detail": "connection reset" },
    "langgraph-server": { "status": "up", "latency_ms": 4 },
    "ollama":           { "status": "up", "latency_ms": 120 }
  }
}
```
`status ∈ up | degraded | down`；Redis 为 non-critical（降级不阻断 ready）；**Postgres 在 J23 下同样为非阻断依赖**，down 时 `/ready` 仍返回 `200` 并携 `X-Degraded: no-persistence`，由 langgraph-server 的 ephemeral store 接管，run 仍可完成（仅不落库）。**响应头同步输出汇总的 `X-Degraded`。**

### 3.10 /admin/* —— 管理接口组（仅 `role=admin`）

统一约定：鉴权 JWT 且 `role=admin`，否则 `AUTH_403_FORBIDDEN`；全部写审计日志。

| 方法 路径 | 请求体 | 响应 | 说明 |
|-----------|--------|------|------|
| POST /admin/cache/clear | `{ "scope": "l1"\|"l2"\|"all", "doc_id"? }` | `{ "purged": 123 }` | 按 doc_id 反查清除受影响缓存（失效联动） |
| POST /admin/index/rebuild | `{ "scope": "vector"\|"graph"\|"fulltext"\|"all", "full": true }` | `202 { "task_id": "t_x1" }` | 异步重建；进度查 `GET /admin/tasks/{task_id}` |
| PUT /admin/config/hot-reload | `{}` | `{ "reloaded": ["cleaning_rules","pipeline_config"] , "errors": [] }` | J18 受限热更（§7 of 01） |
| GET /admin/review-queue | query: `cursor`,`limit` | `{ items:[{entity_id,name,freq,first_seen}], next_cursor }` | J12 开放区人工审核队列（按出现频次排序） |
| POST /admin/review/decision | `{ "entity_id": "...", "action": "approve"\|"reject" }` | `{ "ok": true }` | approve → 升级白名单并重放关联三元组 |
| GET /admin/tasks/{task_id} | — | `{ "state":"running"\|"done"\|"failed", "progress": 0.42 }` | 重建任务进度 |

### 3.11 /admin/debug/* —— 调试与管道预览接口组

统一约定：鉴权同 §3.10（JWT+admin）；全部为**只读或显式触发型**调试端点，生产环境可通过配置整体禁用（`admin.debug_enabled=false` 时返回 `SYS_403_DEBUG_DISABLED`）。括号内为关联子阶段单元号（01 §6）。

| 方法 路径 | 请求体 / Query | 响应 | 用途（单元） |
|-----------|----------------|------|--------------|
| POST /admin/ingestion/run | `{ "mode": "full"\|"incremental", "source"? }` | `202 { task_id }` | 触发采集扫描（1.1） |
| GET /admin/ingestion/scans | `cursor`,`limit` | `{ items:[{scan_id,mode,discovered,changed,deduped,finished_at}], next_cursor }` | 扫描结果列表（1.1） |
| POST /admin/parsing/preview | `{ doc_id }` 或 multipart 文件 | `{ text, structure_tree[], format_meta }` | 解析预览（1.2） |
| POST /admin/cleaning/preview | `{ doc_id, rules_override? }` | `{ before, after, removed_spans[], quality_score }` | 清洗 diff（1.3） |
| POST /admin/chunking/preview | `{ doc_id }` | `{ chunks:[{chunk_id,content,title_path,position}] }` | 分块边界预览（2.1） |
| POST /admin/debug/embed | `{ "text": string }` | `{ dense_dims: 1024, sparse_keys: int, latency_ms }` | 向量探针（2.3） |
| GET /admin/qdrant/points | `doc_id` | `{ points:[{id,score?,payload}] }` | payload 查看（3.1） |
| POST /admin/debug/analyze | `{ "index": "rag_entities\|rag_chunks", "text": string }` | `{ tokens:[...] }` | IK 分词调试（3.2） |
| POST /admin/debug/retrieve | `{ query, top_k=10, sources[] }`（sources ⊆ 六路枚举，缺省全选） | `{ results: { "<source>": RetrievalResult[] }, fused: Top-N }` | 六路检索+融合对比（3.3-3.5） |
| POST /admin/debug/rerank | `{ query, docs:[{content}] , top_k? }` | `{ ranked:[{content,score}] , degraded:false, elapsed_ms }` | 精排对比（4.1） |
| GET /admin/communities | `level?`, `cursor` | `{ items:[{community_id,level,summary,size}], next_cursor }` | 社区摘要浏览（2.6） |
| GET /admin/golden/export | `since?` | CSV 流（点踩 bad case 清单） | golden 回流（7.2） |

**错误码补充**：`DEBUG_400_INVALID_SOURCE`（sources 含非法枚举）、`SYS_403_DEBUG_DISABLED`（生产禁用态）。

## 4. Agent 面契约（langgraph-server，SDK 视角）

前端经 `@langchain/langgraph-sdk` 直连（J19）。以下为实际生效的 REST 形态，前端一般不手写 HTTP 而使用 SDK 方法。

| 操作 | SDK 方法 | HTTP 形态 |
|------|----------|-----------|
| 创建会话线程 | `client.threads.create()` | `POST /threads` → `{thread_id}` |
| 发起流式运行 | `client.runs.stream(threadId, assistantId, {...})` | `POST /threads/{tid}/runs/stream` |
| 取终态 | `client.threads.getState(threadId)` | `GET /threads/{tid}/state` |
| 中断恢复(HITL 预留) | `client.runs.join(threadId, runId)` | `POST /threads/{tid}/runs/{rid}/join` |

**发起运行的输入约定**（与 AgentState 对齐，架构 §3.4）：

```js
const stream = client.runs.stream(threadId, "rag_agent", {
  input: {
    original_query: "清蒸鲈鱼怎么做好吃？",
    session_id: "s_a1b2c3",
    user_id: "u_9f8a7b6c"
  },
  config: {
    configurable: {
      latency_tier: "standard",        // fast | standard | deep | auto(默认)
      model: null                      // null = 使用 generator 角色默认条目 (J2)
    }
  },
  streamMode: ["updates", "messages-tuple"]
});
```

- 会话线程状态由 Postgres checkpoint 承载（J21）；多轮对话无需前端回传历史
- 流式事件帧协议、事件类型与打字机时序约定 → 见 **03 通信协议规范**
- 认证：同源 JWT，经 server 的 custom auth 校验（头同为 `Authorization: Bearer`）

## 5. 核心数据类型（JSON Schema 形式）

> Pydantic 权威定义在 `app/core/models.py` 与 `app/api/models.py`（D1）；此处为对外稳定子集。

| 类型 | 字段 | 说明 |
|------|------|------|
| ChatRunInput | `original_query: string`(必填, ≤2000字) · `session_id: string` · `user_id: string` | run 入参 |
| RunConfig | `configurable.latency_tier: "auto"\|"fast"\|"standard"\|"deep"` · `configurable.model: string\|null` | auto 由意图路由定档（D4） |
| Citation | `marker: int` · `result_ids: string[]` · `quote: string\|null` | 引用标注（架构 3.3） |
| AssistantMessage | `message_id` · `content` · `citations[]` · `degraded: bool` · `latency_tier` · `model` · `created_at` | 03 §4 终态事件的载荷同构 |
| SubgraphResponse | `nodes[{id,label,type,zone}]` · `relationships[{source,target,type}]` | NVL 直连格式 |
| PrecheckHit | `hit:true` · `answer` · `citations[]` · `cache_score` · `matched_query` | H2 |
| HealthStatus | `status` · `components{name:{status,latency_ms?,detail?}}` | §3.9 |
| SessionSummary | `session_id` · `title` · `message_count` · `created_at` · `updated_at` | §3.2 |
| FeedbackRequest | `session_id` · `message_id` · `rating` · `reason?` · `comment?` | §3.5 |

## 6. 错误码总表

命名空间：`AUTH_` 认证 · `CHAT_` 聊天链路 · `SESSION_` 会话 · `FEEDBACK_` 反馈 · `GRAPH_` 图谱 · `ADMIN_` 管理 · `SYS_` 系统。

| 错误码 | HTTP | 触发场景 | 前端建议处理 |
|--------|------|----------|--------------|
| AUTH_400_BAD_CREDENTIALS | 400 | 用户名密码错误 | 提示重新输入 |
| AUTH_401_INVALID_API_KEY | 401 | API Key 不存在或停用 | 检查 .env 配置 |
| AUTH_401_TOKEN_EXPIRED | 401 | JWT 过期 | 静默重走 /auth/token，失败则跳登录页 |
| AUTH_401_TOKEN_INVALID | 401 | 签名校验失败 | 同上 |
| AUTH_403_FORBIDDEN | 403 | 非 admin 访问 /admin/* | 提示无权限 |
| AUTH_429_RATE_LIMITED | 429 | 兑换/请求限流 | 退避重试（Retry-After 头优先） |
| CHAT_400_EMPTY_QUERY | 400 | 空查询 | 输入校验前置拦截 |
| CHAT_400_INVALID_TIER | 400 | latency_tier 非法 | 下拉框约束避免 |
| CHAT_404_THREAD_NOT_FOUND | 404 | thread 不存在/已删除 | 引导新建会话 |
| CHAT_429_RATE_LIMITED | 429 | 并发/频率超限 | 显示排队提示 |
| CHAT_504_TIER_TIMEOUT | 504 | 超 wall_clock_budget（M3/B4） | 展示已生成的部分结果 + 重试按钮 |
| SESSION_404_NOT_FOUND | 404 | 会话不存在或非本人 | 刷新会话列表 |
| FEEDBACK_404_MESSAGE_NOT_FOUND | 404 | 消息不存在 | 忽略静默失败 |
| GRAPH_404_ENTITY_NOT_FOUND | 404 | 实体未收录 | 提示换词 |
| GRAPH_503_STORE_UNAVAILABLE | 503 | Neo4j down（no-graph 降级中） | 顶栏 DegradedBanner |
| ADMIN_409_TASK_RUNNING | 409 | 重建任务已在执行 | 轮询 tasks 接口 |
| SYS_500_INTERNAL | 500 | 未归类内部错误 | 通用错误页 + 反馈入口 |
| SYS_403_DEBUG_DISABLED | 403 | 生产环境禁用 /admin/debug/* | 隐藏调试入口 |
| DEBUG_400_INVALID_SOURCE | 400 | debug/retrieve 的 sources 含非法枚举 | 检查取值 |
| SYS_503_DEPENDENCY_DOWN | 503 | 关键依赖 down（/ready 失败同源） | 服务暂不可用文案 |

> 新增错误码必须落在本表并同步 03 §6（通信相关子集）、06 §9（文案映射）。

## 7. TypeScript 类型对照

```ts
// types/api.ts —— 与本文件 §5 一一对应
export type LatencyTier = "auto" | "fast" | "standard" | "deep";
export type UserRole = "user" | "admin";

export interface Citation { marker: number; result_ids: string[]; quote: string | null; }

export interface ChatRunInput {
  original_query: string;
  session_id: string;
  user_id: string;
}
export interface RunConfigurable { latency_tier?: LatencyTier; model?: string | null; }

export interface AssistantMessage {
  message_id: string;
  content: string;
  citations: Citation[];
  degraded: boolean;
  latency_tier: Exclude<LatencyTier, "auto">;
  model: string | null;
  created_at: string; // ISO 8601 UTC
}

export interface SessionSummary {
  session_id: string; title: string; message_count: number;
  created_at: string; updated_at: string;
}
export interface Paged<T> { items: T[]; next_cursor: string | null; }

export interface PrecheckResponse {
  hit: boolean;
  answer?: string; citations?: Citation[];
  cache_score?: number; matched_query?: string;
  suggested_run?: { latency_tier: Exclude<LatencyTier, "auto"> };
}

export interface GraphNode { id: string; label: string; type: string; zone: "core" | "open"; }
export interface GraphEdge { source: string; target: string; type: string; }
export interface SubgraphResponse { nodes: GraphNode[]; relationships: GraphEdge[]; }

export interface PublicConfig {
  models: { id: string; label: string; provider: "cloud" | "local" }[];
  latency_tiers: Exclude<LatencyTier, "auto">[];
  compression_strategies: ("llm_extract" | "extractive" | "none")[];
  profile: "cloud-primary" | "local-full";
}

export type SourceKind = "dense" | "sparse" | "graph" | "global" | "fulltext" | "web";

export interface PlanStep {
  step_id: string;
  tool: SourceKind | "direct_answer";
  query: string;
  depends_on: string[];
  status: "pending" | "running" | "done" | "skipped";
}

export interface ReflectFeedback {
  sufficient: boolean;
  missing_aspects: string[];
  followup_queries: string[];
}

export interface DebugRetrieveResponse {
  results: Partial<Record<SourceKind, { result_id: string; content: string; score: number; doc_id: string | null }[]>>;
  fused: { result_id: string; content: string }[];
}

export interface ApiError { code: string; message: string; detail?: unknown; }

// 降级原因：与 02 §2.4 逐值对齐；前端 06 §9 Banner 文案须全覆盖
export type DegradedReason =
  | "no-graph" | "no-rerank" | "llm-fallback" | "no-memory"
  | "no-cache" | "budget-exhausted" | "no-persistence";

// Agent 图节点名（thought 聚合源）：与 03 §3.3/§3.4 权威枚举一致；
// 前端 summarize() 须对全部成员穷举 switch，未覆盖即 tsc 报错
export type AgentNodeName =
  | "load_memory" | "query_understanding" | "planner"
  | "tool_router" | "reflector" | "generator" | "self_correction";
```

---

*变更记录：v1.0（2026-08-23）基于《GraphRAG 系统架构文档 v3.0》§2.2/§3.3/§3.6 创建。*
