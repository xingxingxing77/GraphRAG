/**
 * 六路检索调试端点封装（02 §3.11，单元 3.3-3.5）。
 */
import { http } from "./http";

import type { DebugRetrieveRequest, DebugRetrieveResponse } from "@/types";

/** 六路检索调试（sources 过滤 + 分组返回）。
 *
 * 后端同步执行六路并发检索（每路 3s 独立超时），全局 10s 兜底不够用。
 */
export function debugRetrieve(body: DebugRetrieveRequest): Promise<DebugRetrieveResponse> {
  return http
    .post<DebugRetrieveResponse>("/admin/debug/retrieve", body, { timeout: 60_000 })
    .then((r) => r.data);
}
