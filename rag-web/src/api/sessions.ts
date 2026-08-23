/**
 * 会话端点封装（02 §3.2-§3.4）。
 */
import { http } from "./http";

import type { PagedSessionMessage, PagedSessionSummary } from "@/types";

/** 当前用户会话列表（游标分页）。 */
export function listSessions(cursor?: string, limit = 20): Promise<PagedSessionSummary> {
  return http
    .get<PagedSessionSummary>("/sessions", { params: { cursor, limit } })
    .then((r) => r.data);
}

/** 会话历史消息（聚合 checkpoint 与工作记忆）。 */
export function getSessionMessages(
  sessionId: string,
  cursor?: string,
  limit = 50,
): Promise<PagedSessionMessage> {
  return http
    .get<PagedSessionMessage>(`/sessions/${sessionId}/messages`, {
      params: { cursor, limit },
    })
    .then((r) => r.data);
}

/** 删除会话及其记忆（204）。 */
export function deleteSession(sessionId: string): Promise<void> {
  return http.delete(`/sessions/${sessionId}`).then(() => undefined);
}
