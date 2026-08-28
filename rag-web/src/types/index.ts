/**
 * 生成类型便捷别名（types/api.ts 为 openapi-typescript 生成物，J25 禁手改；
 * 本文件仅做 re-export 别名，契约变更经后端 OpenAPI + pnpm gen:api 重生成）。
 */
import type { components } from "./api";

export type Schemas = components["schemas"];

export type Citation = Schemas["Citation"];
export type PrecheckRequest = Schemas["PrecheckRequest"];
export type PrecheckResponse = Schemas["PrecheckResponse"];
export type PublicConfig = Schemas["PublicConfig"];
export type ModelOption = Schemas["ModelOption"];
export type SessionSummary = Schemas["SessionSummary"];
export type SessionMessage = Schemas["SessionMessage"];
export type FeedbackRequest = Schemas["FeedbackRequest"];
export type SubgraphResponse = Schemas["SubgraphResponse"];
export type TokenResponse = Schemas["TokenResponse"];
export type UserInfo = Schemas["UserInfo"];
export type AuthTokenRequest = Schemas["AuthTokenRequest"];
export type HealthStatus = Schemas["HealthStatus"];

export type PagedSessionSummary = Schemas["Paged_SessionSummary_"];
export type PagedSessionMessage = Schemas["Paged_SessionMessage_"];

// 采集调试（02 §3.11，单元 1.1）
export type IngestionRunRequest = Schemas["IngestionRunRequest"];
export type ScanRecord = Schemas["ScanRecord"];
export type PagedScanRecord = Schemas["Paged_ScanRecord_"];
export type TaskAccepted = Schemas["TaskAccepted"];

// 解析预览（02 §3.11，单元 1.2）
export type ParsingPreviewResponse = Schemas["ParsingPreviewResponse"];
export type StructureNode = Schemas["StructureNode"];

// 清洗预览（02 §3.11，单元 1.3）
export type CleaningPreviewRequest = Schemas["CleaningPreviewRequest"];
export type CleaningPreviewResponse = Schemas["CleaningPreviewResponse"];

// 分块预览（02 §3.11，单元 2.1）
export type ChunkingPreviewRequest = Schemas["ChunkingPreviewRequest"];
export type ChunkingPreviewResponse = Schemas["ChunkingPreviewResponse"];
export type Chunk = Schemas["Chunk"];
export type PositionMeta = Schemas["PositionMeta"];

// 向量探针（02 §3.11，单元 2.3）
export type EmbedProbeRequest = Schemas["EmbedProbeRequest"];
export type EmbedProbeResponse = Schemas["EmbedProbeResponse"];

// 社区摘要浏览（02 §3.11，单元 2.6）
export type CommunitySummaryItem = Schemas["CommunitySummaryItem"];
export type PagedCommunitySummaryItem = Schemas["Paged_CommunitySummaryItem_"];

// Qdrant points 查看（02 §3.11，单元 3.1）
export type QdrantPointItem = Schemas["QdrantPointItem"];
export type QdrantPointsResponse = Schemas["QdrantPointsResponse"];

// IK 分词调试（02 §3.11，单元 3.2）
export type IkAnalyzeRequest = Schemas["IkAnalyzeRequest"];
export type IkAnalyzeResponse = Schemas["IkAnalyzeResponse"];

// 六路检索调试（02 §3.11，单元 3.3-3.5）
export type DebugRetrieveRequest = Schemas["DebugRetrieveRequest"];
export type DebugRetrieveResponse = Schemas["DebugRetrieveResponse"];

// 精排对比调试（02 §3.11，单元 4.1）
export type DebugRerankRequest = Schemas["DebugRerankRequest"];
export type DebugRerankResponse = Schemas["DebugRerankResponse"];
export type DebugRerankRankedItem = Schemas["DebugRerankRankedItem"];

/**
 * Agent 面/内部契约类型（02 §7 镜像）：不经业务面 OpenAPI，
 * 由 03/02 直接定义（R7 差异登记于 0.6 契约冻结）。禁止手改生成物，
 * 但本段为 02 §7 的人读镜像落地，变更须同步 02。
 */
export type LatencyTier = "auto" | "fast" | "standard" | "deep";

export interface ChatRunInput {
  original_query: string;
  session_id: string;
  user_id: string;
  /** 显式延迟档位（D4；auto 由 query_understanding 定档回写实际档位，02 §5） */
  latency_tier: LatencyTier;
  /** 请求级模型覆盖（J2，registry 条目名；null 用 generator 默认链） */
  model?: string | null;
}

/** run config.configurable（C6 后已不再承载 tier/model，保留给未来扩展） */
export interface RunConfigurable {
  latency_tier?: LatencyTier;
  model?: string | null;
}

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

export interface ApiError {
  code: string;
  message: string;
  detail?: unknown;
}

export type SourceKind = "dense" | "sparse" | "graph" | "global" | "fulltext" | "web";

export type UserRole = "user" | "admin";

/** 游标分页泛型（02 §5/§7；OpenAPI 生成物中展开为 Paged_* 具体化） */
export interface Paged<T> {
  items: T[];
  next_cursor: string | null;
}

/** 图谱关系边（02 §7 命名；生成物中为 GraphRelationship） */
export type GraphEdge = Schemas["GraphRelationship"];
export type GraphNode = Schemas["GraphNode"];

/** assistant 消息（03 §4 终态事件载荷同构，02 §7） */
export interface AssistantMessage {
  message_id: string;
  content: string;
  citations: Citation[];
  degraded: boolean;
  latency_tier: Exclude<LatencyTier, "auto">;
  model: string | null;
  created_at: string;
}

/** 降级原因（与 02 §2.4 逐值对齐；06 §9 Banner 文案全覆盖） */
export type DegradedReason =
  | "no-graph"
  | "no-rerank"
  | "llm-fallback"
  | "no-memory"
  | "no-cache"
  | "budget-exhausted"
  | "no-persistence";

/** Agent 图节点名（thought 聚合源，02 §7 / 03 §3.3；write_back=写侧尾节点 F4） */
export type AgentNodeName =
  | "load_memory"
  | "query_understanding"
  | "planner"
  | "tool_router"
  | "reflector"
  | "generator"
  | "self_correction"
  | "write_back";
