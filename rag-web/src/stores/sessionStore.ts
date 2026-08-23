/**
 * sessionStore（06 §3）：会话分页列表 + 游标 + 时间分组视图。
 * 线程惰性创建（03 §8）：仅当会话首条消息 precheck miss 且无 thread_id
 * 时才建 thread；本 store 维护 session_id ↔ thread_id 映射。
 * v1.3 布局重规划：新增时间分组派生（今天/7天内/更早）与 activeSession，
 * 由 ChatPage 左侧 WorkspaceSidebar 消费；无独立 /sessions 路由。
 */
import { create } from "zustand";

import type { SessionSummary } from "@/types";

/** 时间分组键（06 §8 WorkspaceSidebar 分组树）。 */
export type SessionGroupKey = "today" | "week" | "older";

/** 分组结果容器。 */
export interface GroupedSessions {
  today: SessionSummary[];
  week: SessionSummary[];
  older: SessionSummary[];
}

/** 分组显示标签（WorkspaceSidebar 渲染用）。 */
export const SESSION_GROUP_LABELS: Record<SessionGroupKey, string> = {
  today: "今天",
  week: "7 天内",
  older: "更早",
};

/** 分组顺序（树渲染顺序）。 */
export const SESSION_GROUP_ORDER: SessionGroupKey[] = ["today", "week", "older"];

/**
 * 按 updated_at 将会话划分为三组（纯函数，前端派生，02 契约零变更）。
 *
 * 规则（06 §3 v1.3）：与 now 同一自然日 → today；7×24h 内 → week；
 * 其余（含无法解析的日期）→ older。
 *
 * @param sessions - 会话列表（已过滤）。
 * @param now - 参考当前时间（默认 new Date()，测试可注入）。
 * @returns 三组会话。
 */
export function groupSessions(
  sessions: SessionSummary[],
  now = new Date(),
): GroupedSessions {
  const result: GroupedSessions = { today: [], week: [], older: [] };
  for (const s of sessions) {
    const t = s.updated_at ? Date.parse(s.updated_at) : Number.NaN;
    if (Number.isNaN(t)) {
      result.older.push(s);
      continue;
    }
    const d = new Date(t);
    const sameDay =
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate();
    if (sameDay) {
      result.today.push(s);
    } else if (now.getTime() - t < 7 * 24 * 3600 * 1000) {
      result.week.push(s);
    } else {
      result.older.push(s);
    }
  }
  return result;
}

interface SessionState {
  sessions: SessionSummary[];
  nextCursor: string | null;
  loading: boolean;
  /** 当前在侧栏选中的会话（null = 空态/新会话） */
  activeSessionId: string | null;
  /** session_id → thread_id（有 thread 时 thread_id 即 Agent 面标识） */
  threadMap: Record<string, string>;
  loadMore(reset?: boolean): Promise<void>;
  setActive(sessionId: string | null): void;
  bindThread(sessionId: string, threadId: string): void;
  remove(sessionId: string): void;
}

export const useSessionStore = create<SessionState>()((set, get) => ({
  sessions: [],
  nextCursor: null,
  loading: false,
  activeSessionId: null,
  threadMap: {},

  async loadMore(reset = false) {
    const { nextCursor, loading } = get();
    if (loading || (!reset && nextCursor === null && get().sessions.length > 0)) return;
    set({ loading: true });
    try {
      const { listSessions } = await import("@/api/sessions");
      const page = await listSessions(reset ? undefined : (nextCursor ?? undefined));
      const items = page.items ?? [];
      set((s) => ({
        sessions: reset ? items : [...s.sessions, ...items],
        nextCursor: page.next_cursor,
      }));
    } finally {
      set({ loading: false });
    }
  },

  setActive(sessionId) {
    set({ activeSessionId: sessionId });
  },

  bindThread(sessionId, threadId) {
    set((s) => ({ threadMap: { ...s.threadMap, [sessionId]: threadId } }));
  },

  remove(sessionId) {
    set((s) => ({
      sessions: s.sessions.filter((x) => x.session_id !== sessionId),
      activeSessionId: s.activeSessionId === sessionId ? null : s.activeSessionId,
    }));
  },
}));
