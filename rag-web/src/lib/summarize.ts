/**
 * updates 事件聚合（03 §3.5 · 单元 10.3）。
 *
 * thought_steps 为前端本地聚合：由 updates 序列累积生成
 * （node_name + 摘要），服务端不发送该聚合字段。
 * values 终态提取 answer/citations/degraded_reasons/latency_tier。
 */
import type { AgentNodeName, Citation, DegradedReason } from "@/types";

/** 节点增量载荷（宽松结构，按节点名取关键字段）。 */
type NodeDelta = Record<string, unknown>;

/** values 终态提取结果。 */
export interface FinalState {
  answer: string;
  citations: Citation[];
  degradedReasons: DegradedReason[];
  latencyTier: string | null;
}

/** X-Degraded 七枚举（02 §2.4）。 */
const KNOWN_REASONS: DegradedReason[] = [
  "no-graph",
  "no-rerank",
  "llm-fallback",
  "no-memory",
  "no-cache",
  "budget-exhausted",
  "no-persistence",
];

/**
 * 按节点名生成 thought 摘要（03 §3.5）。
 *
 * @param node - 图节点名。
 * @param delta - 该节点状态增量。
 * @returns 人类可读摘要。
 */
export function summarizeNodeUpdate(node: string, delta: NodeDelta): string {
  switch (node) {
    case "load_memory":
      return "注入会话记忆";
    case "query_understanding": {
      const intent = String(delta.intent ?? "");
      const tier = String(delta.latency_tier ?? "");
      return `理解查询（意图 ${intent}${tier ? `，档位 ${tier}` : ""}）`;
    }
    case "planner": {
      const plan = Array.isArray(delta.plan) ? (delta.plan as unknown[]) : [];
      return plan.length > 0 ? `制定检索计划（${plan.length} 步）` : "补充检索计划";
    }
    case "tool_router": {
      const rounds = delta.retrieval_rounds;
      return typeof rounds === "number" ? `执行检索（第 ${rounds} 轮）` : "执行检索";
    }
    case "reflector":
      return delta.needs_more_retrieval === true ? "反思：证据不足，补充检索" : "反思：证据充分";
    case "generator":
      return "生成答案";
    case "self_correction": {
      const score = delta.faithfulness_score;
      return typeof score === "number"
        ? `忠实度校验（${(score * 100).toFixed(0)}%）`
        : "忠实度校验";
    }
    case "write_back":
      return "写入记忆与缓存";
    default:
      return node;
  }
}

/**
 * 从 values 终态提取渲染所需字段。
 *
 * @param values - 图终态 State。
 * @returns 答案/引用/降级原因/实际档位。
 */
export function extractFinalState(values: NodeDelta): FinalState {
  const answer = String(values.answer ?? "");
  const rawCitations = Array.isArray(values.citations) ? (values.citations as Citation[]) : [];
  const rawReasons = Array.isArray(values.degraded_reasons)
    ? (values.degraded_reasons as string[])
    : [];
  const degradedReasons = rawReasons.filter((r): r is DegradedReason =>
    KNOWN_REASONS.includes(r as DegradedReason),
  );
  const tier = values.latency_tier;
  return {
    answer,
    citations: rawCitations,
    degradedReasons,
    latencyTier: typeof tier === "string" ? tier : null,
  };
}

/** 判断节点名是否为合法 AgentNodeName（thought 面板过滤）。 */
export function isAgentNode(node: string): node is AgentNodeName {
  return [
    "load_memory",
    "query_understanding",
    "planner",
    "tool_router",
    "reflector",
    "generator",
    "self_correction",
    "write_back",
  ].includes(node);
}

/**
 * 从 messages-tuple 事件提取增量文本（J8 fast 档逐 token 直推）。
 *
 * 载荷可能为 [message, metadata] 元组或 message 本体；content 兼容
 * string 与内容块数组（{type:"text", text}）两种形态。
 *
 * @param payload - messages 事件 data。
 * @returns 增量文本（无可提取内容返回空串）。
 */
export function extractMessageChunk(payload: unknown): string {
  const msg = (Array.isArray(payload) ? payload[0] : payload) as
    | { content?: unknown }
    | undefined;
  const content = msg?.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((p) =>
        typeof p === "string"
          ? p
          : String((p as { text?: string } | null)?.text ?? ""),
      )
      .join("");
  }
  return "";
}
