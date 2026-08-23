/**
 * 清洗预览端点封装（02 §3.11，单元 1.3）。
 */
import { http } from "./http";

import type { CleaningPreviewRequest, CleaningPreviewResponse } from "@/types";

/** 清洗前后对比预览。 */
export function previewCleaning(
  body: CleaningPreviewRequest,
): Promise<CleaningPreviewResponse> {
  return http
    .post<CleaningPreviewResponse>("/admin/cleaning/preview", body)
    .then((r) => r.data);
}
