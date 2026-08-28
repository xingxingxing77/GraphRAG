/**
 * 采集调试端点封装（02 §3.11，单元 1.1）。
 */
import { http } from "./http";

import type { IngestionRunRequest, PagedScanRecord, TaskAccepted } from "@/types";

/** 触发采集扫描（full | incremental），202 + task_id。
 *
 * 后端同步执行全量扫描（full 档遍历语料目录），全局 10s 兜底不够用。
 */
export function runIngestion(body: IngestionRunRequest): Promise<TaskAccepted> {
  return http
    .post<TaskAccepted>("/admin/ingestion/run", body, { timeout: 120_000 })
    .then((r) => r.data);
}

/** 扫描结果列表（游标分页）。 */
export function listScans(cursor?: string, limit = 20): Promise<PagedScanRecord> {
  return http
    .get<PagedScanRecord>("/admin/ingestion/scans", { params: { cursor, limit } })
    .then((r) => r.data);
}
