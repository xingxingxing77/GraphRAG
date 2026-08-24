/**
 * Qdrant 调试端点封装（02 §3.11，单元 3.1）。
 */
import { http } from "./http";

import type { QdrantPointsResponse } from "@/types";

/** 按 doc_id 查 points（payload 查看）。 */
export function getPoints(docId: string, limit = 100): Promise<QdrantPointsResponse> {
  return http
    .get<QdrantPointsResponse>("/admin/qdrant/points", {
      params: { doc_id: docId, limit },
    })
    .then((r) => r.data);
}
