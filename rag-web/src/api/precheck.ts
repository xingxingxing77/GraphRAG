/**
 * 缓存短路端点封装（02 §3.8 POST /chat/precheck，J22/H2）。
 * 异常按 miss 处理，绝不阻塞主链路（03 §8）。
 */
import { http } from "./http";

import type { PrecheckRequest, PrecheckResponse } from "@/types";

/** L1 语义缓存短路查询。 */
export function precheck(body: PrecheckRequest): Promise<PrecheckResponse> {
  return http.post<PrecheckResponse>("/chat/precheck", body).then((r) => r.data);
}
