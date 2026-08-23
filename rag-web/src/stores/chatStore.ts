/**
 * chatStore（06 §3）：单会话视图态。
 * 字段与后端 AgentState 对齐评审（单元 0.5 S2）；thoughtSteps 由
 * updates 事件聚合（03 §3.5，服务端不下发聚合字段）。
 */
import { create } from "zustand";

import type { AgentNodeName, Citation, DegradedReason } from "@/types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  degraded?: boolean;
  cacheHit?: boolean;
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
  /** 用户选择档位，默认 standard */
  activeTier: "fast" | "standard" | "deep";
  appendUserMessage(query: string): void;
  appendAssistant(msg: Omit<ChatMessage, "id" | "role">): void;
  setStreaming(v: boolean): void;
  pushThoughtStep(node: AgentNodeName, summary: string): void;
  setFinalAnswer(answer: string, citations: Citation[], reasons: DegradedReason[]): void;
  consumeTypewriter(): void;
  pushDegraded(reasons: string[]): void;
  setActiveTier(tier: "fast" | "standard" | "deep"): void;
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
  activeTier: "standard",

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

  setStreaming(v) {
    set({ streaming: v });
  },

  pushThoughtStep(node, summary) {
    set((s) => ({ thoughtSteps: [...s.thoughtSteps, { node, summary }] }));
  },

  setFinalAnswer(answer, citations, reasons) {
    const { degradedReasons } = get();
    set({
      typewriterTarget: answer,
      degradedReasons: Array.from(new Set([...degradedReasons, ...reasons])),
    });
    get().appendAssistant({
      content: answer,
      citations,
      degraded: reasons.length > 0,
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

  setActiveTier(tier) {
    set({ activeTier: tier });
  },

  reset() {
    set({
      messages: [],
      streaming: false,
      thoughtSteps: [],
      typewriterTarget: null,
      degradedReasons: [],
    });
  },
}));
