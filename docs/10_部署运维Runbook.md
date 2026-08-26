# 10 部署运维 Runbook（D9 集中化）

> **版本**: v1.0 | **日期**: 2026-08-23 | **受众**: 运维 / SRE
> **上游依据**: 架构文档 D9 部署拓扑、`01_开发流程.md` §7 配置、`04_数据库设计.md` 存储、`02_API接口契约.md` §2.4 / §3.9 降级与就绪、`03_通信协议规范.md` §5 降级信号。
> **定位**: 把散落在架构文档与 `01 §7` 的部署/降级/备份信息集中为可操作 SOP。存储 schema/命名以 `04` 为权威，本节仅补运维操作命令；存储缓存/异步写策略背景见 `11_数据库与缓存实施路线图.md`。

---

## 1. 部署拓扑（D9）

`docker compose` 服务与启动顺序（依赖在前）：

1. **存储**：`postgres`(16) → `qdrant`(≥1.10) / `neo4j`(5.x community) / `elasticsearch`(8.x+IK) / `redis`(7.x AOF)
2. **应用**：`app`(FastAPI 业务面 :8000) → `langgraph-server`(:8001) → `ollama`(本地模型，可选)
3. **前端**：`rag-web`(Vite :5173 开发) / 反代后生产

端口与依赖见 `01_开发流程.md`；`docker compose up -d` 起全栈，`curl http://localhost:8000/ready` 全绿后开工（README 快速开始）。

## 2. 环境变量集中表

来源：`01 §7` + `06_前端开发指南.md` §1 `.env.local`。**密钥仅经环境变量，禁入前端 bundle**（AGENT #7 / J16/D7）。

| 变量 | 用途 | 备注 |
|------|------|------|
| `POSTGRES_DSN` | Postgres 连接 | langgraph checkpoint（J21） |
| `QDRANT_URL` | 向量库 | ≥1.10 |
| `NEO4J_URI` / `NEO4J_AUTH` | 图谱 | community 版 |
| `ES_URL` | 全文索引 | IK 插件 |
| `REDIS_URL` | 工作记忆 / L2 / 限流 | AOF |
| `JWT_SECRET` | 双服务共享签名密钥（HS256） | app 与 langgraph-server 必须一致（J16/J19） |
| `X-API-Key` / 服务 Key | 兑换 / 服务间调用 | 仅环境变量（`api_key_ref`） |
| `DEBUG_ENABLED` | admin 调试端点总开关 | `false`（fail-closed，D7）；dev 置 `true` 开 `/admin/debug/*`（`SYS_403_DEBUG_DISABLED`） |
| `VITE_API_BASE` | 前端→业务面 | `http://localhost:8000/api/v1` |
| `VITE_AGENT_BASE` | 前端→langgraph | `http://localhost:8001` |
| `VITE_AGENT_ASSISTANT` | 图 assistant_id | `agent` |

CORS：业务面白名单含 `http://localhost:5173`（dev）；Agent 面经 SDK 直连受 custom auth + CORS 约束（06 §1）。

## 3. 健康检查 SOP

- 存活：`GET /health`（进程级）。
- 就绪：`GET /ready`（依赖聚合）。任一 **critical** 依赖 down → 503；**Redis / Postgres 为非阻断**（Postgres down 仍 200 + `X-Degraded: no-persistence`，J23）。

巡检：

```bash
curl -s http://localhost:8000/ready | jq '.status, .components'
```

- 响应头汇总 `X-Degraded`（多值逗号分隔）即当前降级态（见 §5）。
- `status ∈ up | degraded | down`；`ready` 全绿 = 所有组件 up。

**环境就绪后的 L2 联调自测**（01 §6.11 单元 10.4，用户环境落地后执行）：

```bash
docker compose up -d                 # 五存储 + app:8000 + langgraph-server:8001
# .env 填真实密钥（JWT_SECRET 双服务一致、LLM/Tavily Key 按需）
curl http://localhost:8000/ready     # 全绿前置
python scripts/l2_smoke.py           # 人工演示口径（三档基准对话，逐项 PASS/FAIL）
pytest tests/integration -v          # 正式断言口径（S-01~S-04）
```

## 4. 存储备份与恢复

> schema/命名以 `04_数据库设计.md` 为权威；本节为运维操作命令。

| 存储 | 备份 | 恢复 | RPO/RTO |
|------|------|------|---------|
| Postgres | `pg_dump -Fc rag > pg_$(date +%F).dump`（每日全量）+ WAL 归档（04 §2.2） | `pg_restore -d rag pg_*.dump` | PITR 7 天 |
| Qdrant | `curl -X POST localhost:6333/collections/{c}/snapshots` 并取回 | 上传快照恢复 | 依快照频率 |
| Neo4j | `neo4j-admin database dump --to-path=/backup` | `neo4j-admin database load` | 依调度 |
| Elasticsearch | snapshot API（注册仓库后 `PUT _snapshot/rag_backup/{name}`） | `POST _snapshot/rag_backup/{name}/_restore` | 依调度 |
| Redis | AOF（`appendonly yes`）+ `BGSAVE`；`appendfsync everysec` | 重启自动 AOF 重放 | 秒级 |

注意：Qdrant/Neo4j/ES 可重建派生或管道重跑；**Postgres checkpoint 为会话 SSOT，优先级最高**。

## 5. 降级开关与处置 SOP（X-Degraded 七值）

权威定义见 `02 §2.4`；前端文案见 `06 §9`（已与 02 逐值对齐，`08` R1 双向校验）。

| 取值 | 含义 | 运维动作 |
|------|------|----------|
| `no-graph` | Neo4j 不可用，跳 graph/fulltext/global | 查 Neo4j 容器/连接；恢复后自动恢复，无需操作 |
| `no-rerank` | Reranker 故障，退粗排 Top-K | 查 rerank 服务/超时；可 `PUT /admin/config/hot-reload`（02 §3.10） |
| `llm-fallback` | 主模型失败，切轻量模型 | 查主模型服务/配额；观察答案质量 |
| `no-memory` | Redis 不可用，记忆跳过 | 查 Redis；工作记忆 AOF 保护，恢复后接续 |
| `no-cache` | Qdrant/Redis 缓存不可用，precheck 按 miss | 查缓存层；不阻塞主链路（J22） |
| `budget-exhausted` | 预算耗尽强制降级作答 | 观察复杂度；非故障，仅提示不完整 |
| `no-persistence` | Postgres/checkpoint 不可用，ephemeral 运行 | **答案仍返回但不落库**；顶栏提示"对话未保存"；重建索引/会话删除在 ephemeral 态跳过（J23）；Postgres 恢复后历史不可恢复，需告知用户 |

SSE 流内 `X-Degraded` 启动即知 + `values.degraded_reasons` 终态；REST 通道经响应头（03 §5）。

## 6. 监控告警

- **磁盘**：单机 compose 默认配额 **≥50GB**，各卷监控告警（04 §8）；Qdrant/ES/Neo4j 容量随 chunks 线性增长，按 1 万 chunks 口径预估。
- **性能**：`GPU 显存峰值 <22GB`（07 §性能）；Qdrant/ES P99、全局 semaphore 排队深度。
- **降级**：`no-persistence`/`no-graph` 等持续超阈值 → 告警。

## 7. 常见故障处置

| 现象 | 可能原因 | 处置 |
|------|----------|------|
| `/ready` 503 | critical 依赖 down | 查 components 定位；按 §4 恢复 |
| 答案不落库 / 历史丢失 | Postgres down（`no-persistence`） | 恢复 Postgres；告知用户 ephemeral 态历史不可恢复（J23） |
| 图谱类答案缺失 | Neo4j down（`no-graph`） | 恢复 Neo4j；期间已降级为向量检索 |
| 多轮指代失准 | Redis down（`no-memory`） | 恢复 Redis；工作记忆 AOF 接续 |
| precheck 恒 miss / 慢 | Qdrant/Redis 缓存层（`no-cache`） | 查缓存；主链路不受影响 |
| 重建卡住 | 索引任务 running | `GET /admin/tasks/{id}` 轮询；`ADMIN_409_TASK_RUNNING` 时勿重复触发（02 §6） |

## 8. 索引 / 重建触发

- 触发：`POST /admin/index/rebuild {scope, full}` → `202 {task_id}`（02 §3.10）。
- 进度：`GET /admin/tasks/{id}`（`state` / `progress`）。
- 热更（受限）：`PUT /admin/config/hot-reload`（清洗/检索权重/降级参数，J18）；分块/embedding 变更必须走重建。
- ES 别名零停机重建：`rag_entities_v{n}` → 校验 count → 切别名 → 删旧（04 §6.4）。

---

*变更记录：v1.0（2026-08-23）依据架构 D9 / 01 §7 / 04 / 02 §2.4·§3.9 / 03 §5 创建，补齐 G7 运维缺口。v1.1（2026-08-26）§3 新增环境就绪后的 L2 联调自测路径（docker compose 全栈 + .env 真实密钥 + /ready 全绿 → scripts/l2_smoke.py / pytest tests/integration 双口径），对齐单元 10.4 harness 交付。v1.2（2026-08-26）§2 环境变量表新增 `DEBUG_ENABLED`（admin 调试端点总开关，fail-closed，D7/BUG-10）。*
