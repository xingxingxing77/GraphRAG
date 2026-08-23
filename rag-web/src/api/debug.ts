/**
 * 调试端点封装（02 §3.11，随关联单元扩展）。
 */
import { http } from "./http";

import type { EmbedProbeRequest, EmbedProbeResponse } from "@/types";

/** 向量探针（单元 2.3）：dense 维数 / sparse 键数 / 耗时。 */
export function probeEmbed(body: EmbedProbeRequest): Promise<EmbedProbeResponse> {
  return http
    .post<EmbedProbeResponse>("/admin/debug/embed", body)
    .then((r) => r.data);
}
