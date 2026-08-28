/**
 * chatStore（06 §3）：单会话视图态。
 * 字段与后端 AgentState 对齐评审（单元 0.5 S2）；thoughtSteps 由
 * updates 事件聚合（03 §3.5，服务端不下发聚合字段）。
 */
import { create } from "zustand";

import type { AgentNodeName, Citation, DegradedReason } from "@/types";

export interface ChatMessage {
  id: string;
  /** 后端消息 ID（会话历史/反馈用；本地新消息为占位 id） */
  messageId?: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  degraded?: boolean;
  cacheHit?: boolean;
  /** fast 档逐 token 直推中的活跃消息（values 终态到达时被替换） */
  live?: boolean;
  /** 实际执行档位（auto 由 query_understanding 定档回写，架构 2.4 v3.1） */
  latencyTier?: string;
  /** deep 档已复核标识（7.1：忠实度校验通过） */
  verified?: boolean;
  createdAt?: string;
}

export interface ThoughtStep {
  node: AgentNodeName;
  summary: string;
}

interface ChatState {
  messages: ChatMessage[];
  streaming: boolean;
  thoughtSteps: ThoughtStep[];
  /** 终态 answer，TypewriterText 消费后置空 */
  typewriterTarget: string | null;
  degradedReasons: DegradedReason[];
  /** 用户选择档位，默认 auto（意图路由定档，D4） */
  activeTier: "auto" | "fast" | "standard" | "deep";
  /** 用户选择的模型条目（J2 请求级覆盖；空串 = 默认条目） */
  model: string | null;
  /** 重生成提示（SSE updates.generator.regenerated） */
  regenerating: boolean;
  /** deep 档忠实度评分（SSE updates.self_correction.faithfulness_score） */
  faithfulnessScore: number | null;
  appendUserMessage(query: string): void;
  appendAssistant(msg: Omit<ChatMessage, "id" | "role">): void;
  /** fast 档逐 token 直推（J8）：追加到活跃 live 消息（无则新建） */
  appendStreamChunk(chunk: string): void;
  setStreaming(v: boolean): void;
  pushThoughtStep(node: AgentNodeName, summary: string): void;
  setFinalAnswer(
    answer: string,
    citations: Citation[],
    reasons: DegradedReason[],
    latencyTier?: string | null,
  ): void;
  consumeTypewriter(): void;
  pushDegraded(reasons: string[]): void;
  clearDegraded(): void;
  clearThoughts(): void;
  setActiveTier(tier: "auto" | "fast" | "standard" | "deep"): void;
  setModel(model: string | null): void;
  setRegenerating(v: boolean): void;
  setFaithfulnessScore(score: number | null): void;
  loadHistory(sessionId: string): Promise<void>;
  reset(): void;
}

let msgSeq = 0;
const nextId = () => `m_${Date.now()}_${msgSeq++}`;

export const useChatStore = create<ChatState>()((set, get) => ({
  messages: [],
  streaming: false,
  thoughtSteps: [],
  typewriterTarget: null,
  degradedReasons: [],
  activeTier: "auto",
  model: null,
  regenerating: false,
  faithfulnessScore: null,

  appendUserMessage(query) {
    set((s) => ({
      messages: [...s.messages, { id: nextId(), role: "user", content: query }],
    }));
  },

  appendAssistant(msg) {
    set((s) => ({
      messages: [...s.messages, { id: nextId(), role: "assistant", ...msg }],
    }));
  },

  appendStreamChunk(chunk) {
    set((s) => {
      const last = s.messages[s.messages.length - 1];
      if (last && last.role === "assistant" && last.live) {
        const messages = [...s.messages];
        messages[messages.length - 1] = { ...last, content: last.content + chunk };
        return { messages };
      }
      return {
        messages: [
          ...s.messages,
          { id: nextId(), role: "assistant", content: chunk, live: true },
        ],
      };
    });
  },

  setStreaming(v) {
    set({ streaming: v });
  },

  pushThoughtStep(node, summary) {
    set((s) => ({ thoughtSteps: [...s.thoughtSteps, { node, summary }] }));
  },

  setFinalAnswer(answer, citations, reasons, latencyTier) {
    const { degradedReasons } = get();
    set((s) => ({
      typewriterTarget: answer,
      degradedReasons: Array.from(new Set([...degradedReasons, ...reasons])),
      // fast 档 live 流式消息由终态正式版替换（M1：终态为准）
      messages: s.messages.filter((m) => !m.live),
    }));
    get().appendAssistant({
      content: answer,
      citations,
      degraded: reasons.length > 0,
      latencyTier: latencyTier ?? undefined,
    });
  },

  consumeTypewriter() {
    set({ typewriterTarget: null });
  },

  pushDegraded(reasons) {
    const known = reasons.filter((r): r is DegradedReason =>
      [
        "no-graph",
        "no-rerank",
        "llm-fallback",
        "no-memory",
        "no-cache",
        "budget-exhausted",
        "no-persistence",
      ].includes(r),
    );
    set((s) => ({ degradedReasons: Array.from(new Set([...s.degradedReasons, ...known])) }));
  },

  clearDegraded() {
    set({ degradedReasons: [] });
  },

  clearThoughts() {
    set({ thoughtSteps: [] });
  },

  setActiveTier(tier) {
    set({ activeTier: tier });
  },

  setModel(model) {
    set({ model });
  },

  setRegenerating(v) {
    set({ regenerating: v });
  },

  setFaithfulnessScore(score) {
    set({ faithfulnessScore: score });
  },

  async loadHistory(sessionId) {
    set({
      streaming: false,
      thoughtSteps: [],
      typewriterTarget: null,
      regenerating: false,
      faithfulnessScore: null,
      degradedReasons: [],
    });
    const { getSessionMessages } = await import("@/api/sessions");
    const page = await getSessionMessages(sessionId);
    const items = page.items ?? [];
    set({
      messages: items.map((m) => ({
        id: m.message_id,
        messageId: m.message_id,
        role: m.role,
        content: m.content,
        citations: m.citations,
        degraded: m.degraded,
        latencyTier: m.latency_tier ?? undefined,
        createdAt: m.created_at,
      })),
    });
  },

  reset() {
    set({
      messages: [],
      streaming: false,
      thoughtSteps: [],
      typewriterTarget: null,
      degradedReasons: [],
      model: null,
      regenerating: false,
      faithfulnessScore: null,
    });
  },
}));
