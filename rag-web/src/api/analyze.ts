/**
 * IK 分词调试端点封装（02 §3.11，单元 3.2）。
 */
import { http } from "./http";

import type { IkAnalyzeRequest, IkAnalyzeResponse } from "@/types";

/** IK 分词调试（_analyze 封装）。 */
export function analyzeText(body: IkAnalyzeRequest): Promise<IkAnalyzeResponse> {
  return http
    .post<IkAnalyzeResponse>("/admin/debug/analyze", body)
    .then((r) => r.data);
}
