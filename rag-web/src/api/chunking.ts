/**
 * 分块预览端点封装（02 §3.11，单元 2.1）。
 */
import { http } from "./http";

import type { ChunkingPreviewRequest, ChunkingPreviewResponse } from "@/types";

/** 分块边界预览（解析→清洗→分块）。 */
export function previewChunking(
  body: ChunkingPreviewRequest,
): Promise<ChunkingPreviewResponse> {
  return http
    .post<ChunkingPreviewResponse>("/admin/chunking/preview", body)
    .then((r) => r.data);
}
