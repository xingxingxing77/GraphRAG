/**
 * 六路检索调试端点封装（02 §3.11，单元 3.3-3.5）。
 */
import { http } from "./http";

import type { DebugRetrieveRequest, DebugRetrieveResponse } from "@/types";

/** 六路检索调试（sources 过滤 + 分组返回）。 */
export function debugRetrieve(body: DebugRetrieveRequest): Promise<DebugRetrieveResponse> {
  return http
    .post<DebugRetrieveResponse>("/admin/debug/retrieve", body)
    .then((r) => r.data);
}
