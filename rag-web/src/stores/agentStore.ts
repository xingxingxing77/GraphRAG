/**
 * agentStore（02 §7 / 03 §3.3）：Agent 调试态前端镜像。
 * updates 事件写入侧随单元 10.3（langgraph-server SSE 接线）落地，
 * 当前由 AgentStateInspector 消费快照。
 */
import { create } from "zustand";

/** AgentState 快照（架构 §3.4 字段表前端可见子集）。 */
export interface AgentStateSnapshot {
  query?: string;
  original_query?: string;
  intent?: string;
  latency_tier?: string;
  plan?: { step_id: string; tool: string; query: string; status?: string }[];
  current_step?: number;
  retrieval_rounds?: number;
  needs_more_retrieval?: boolean;
  answer?: string;
  faithfulness_score?: number;
  degraded?: boolean;
  token_budget_exhausted?: boolean;
  received_at?: string;
}

interface AgentStoreState {
  /** 最近一次 updates 事件快照（null = 尚未收到）。 */
  snapshot: AgentStateSnapshot | null;
  /** 写入快照（10.3 SSE 写入侧调用）。 */
  setSnapshot: (snapshot: AgentStateSnapshot) => void;
  /** 清空快照。 */
  clear: () => void;
}

export const useAgentStore = create<AgentStoreState>((set) => ({
  snapshot: null,
  setSnapshot: (snapshot) =>
    set({ snapshot: { ...snapshot, received_at: new Date().toISOString() } }),
  clear: () => set({ snapshot: null }),
}));
