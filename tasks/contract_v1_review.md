# 契约评审记录 · contract-v1（单元 0.6 S3）

> 日期: 2026-08-24 | 依据: 01 §6.1 单元 0.6 · 02 v1.1 · AGENT.md §4
> 状态: 评审通过（前后端各一方以 Agent 角色代审）；**tag `contract-v1` 待用户确认后打**

## 1. 端点就绪度清单（02 §3 ↔ OpenAPI 逐端点核对）

| 端点（02 §3） | 请求模型 | 响应模型 | 状态 |
|---------------|----------|----------|------|
| POST /auth/token（§3.1） | AuthTokenRequest | TokenResponse | 就绪（骨架） |
| GET /sessions（§3.2） | — | Paged[SessionSummary] | 就绪（骨架） |
| GET /sessions/{id}/messages（§3.3） | — | Paged[SessionMessage] | 就绪（骨架） |
| DELETE /sessions/{id}（§3.4） | — | 204 | 就绪（骨架） |
| POST /feedback（§3.5） | FeedbackRequest | FeedbackResponse | 就绪（骨架） |
| GET /graph/subgraph（§3.6） | query/depth≤3/limit≤200 | SubgraphResponse | 就绪（骨架） |
| GET /config/public（§3.7） | — | PublicConfig | 就绪（骨架） |
| POST /chat/precheck（§3.8） | PrecheckRequest | PrecheckResponse | 就绪（骨架） |
| GET /health · /ready（§3.9） | — | HealthStatus（七组件） | 就绪（骨架） |
| /admin/*（§3.10，六端点） | CacheClear/IndexRebuild/ReviewDecision 等 | 对应模型 | 就绪（骨架） |
| /admin/debug/*（§3.11） | — | — | 按关联单元（1.1 起）逐个落地 |

模型定义唯一来源 `app/core/models.py`（D1）；`app/api/models.py` 仅再导出。

## 2. 评审中发现并已修复的缺口

1. **统一错误体不覆盖框架层异常**：Pydantic 校验默认 422、未知路由默认 404 `{"detail":...}`，不符 02 §2.3。已按文档先行流程补登 `SYS_400_VALIDATION` / `SYS_404_NOT_FOUND` 至 02 §6（v1.1）与 06 §9 文案表，并在 `app/main.py` 落地 RequestValidationError / StarletteHTTPException → 统一错误体映射。
2. **R7 类型镜像机制与 J25 生成物冲突**：02 §7 顶层类型 vs openapi-typescript 生成物结构不同源。已升级 R7 校验为「api.ts 生成物 ∪ index.ts 镜像」并豁免脚手架导出，回写 08 R7（v1.3）；前端 `src/types/index.ts` 补齐 02 §7 全部镜像类型。

## 3. 登记遗留项（不阻塞冻结）

| 项 | 归属单元 |
|----|----------|
| sse_schema / degraded_parity 契约门禁接线 | 5.5 / 9.1 |
| R8（summarize 覆盖）启用 | useChatStream 落地（10.4/10.5） |
| R4（bui 依赖黑名单）启用 | 10.7 |
| 各端点业务实现与专属错误码细化 | 10.1（F1）/ 10.2（F2） |
| /admin/debug/* 端点 | 1.1 起按 02 §3.11 关联单元 |
| LangSmith trace 回放（全局 DoD） | 密钥就绪后 |

## 4. 验收动作

- [x] openapi_vs_02 门禁：16 端点双向一致（tests/contract）
- [x] errorcode_parity 门禁：02 §6（22 码）↔ ErrorCode 双向一致
- [x] doc-lint（--frontend rag-web）：硬错误 0
- [x] pytest 全量：55 passed, 2 skipped（占位登记）
- [ ] **tag `contract-v1`**（需用户确认后执行：`git tag contract-v1`）
