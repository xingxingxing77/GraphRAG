/**
 * 解析预览端点封装（02 §3.11，单元 1.2）。
 */
import { http } from "./http";

import type { ParsingPreviewResponse } from "@/types";

/** 上传样例文件解析预览（multipart/form-data）。
 *
 * 后端同步执行「上传+解析」（大 PDF 可达分钟级），全局 10s 兜底不够用。
 */
export function previewFile(file: File): Promise<ParsingPreviewResponse> {
  const form = new FormData();
  form.append("file", file);
  return http
    .post<ParsingPreviewResponse>("/admin/parsing/preview", form, { timeout: 120_000 })
    .then((r) => r.data);
}

/** 按 doc_id 解析预览（最近采集批次）。 */
export function previewByDocId(docId: string): Promise<ParsingPreviewResponse> {
  const form = new FormData();
  form.append("doc_id", docId);
  return http
    .post<ParsingPreviewResponse>("/admin/parsing/preview", form, { timeout: 120_000 })
    .then((r) => r.data);
}
