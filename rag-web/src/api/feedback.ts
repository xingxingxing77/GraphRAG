/**
 * 反馈端点封装（02 §3.5 POST /feedback）。
 */
import { http } from "./http";

import type { FeedbackRequest } from "@/types";

/** 上报点赞/点踩（down 必选 reason）。 */
export function submitFeedback(body: FeedbackRequest): Promise<{ ok: boolean }> {
  return http.post<{ ok: boolean }>("/feedback", body).then((r) => r.data);
}
