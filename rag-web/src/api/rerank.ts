/**
 * 精排对比端点封装（02 §3.11，单元 4.1）。
 */
import { http } from "./http";

import type { DebugRerankRequest, DebugRerankResponse } from "@/types";

/** 精排对比（rerank 前后排序 + 降级标志 + 耗时）。 */
export function debugRerank(body: DebugRerankRequest): Promise<DebugRerankResponse> {
  return http
    .post<DebugRerankResponse>("/admin/debug/rerank", body)
    .then((r) => r.data);
}
