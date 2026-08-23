/**
 * 社区摘要端点封装（02 §3.11，单元 2.6）。
 */
import { http } from "./http";

import type { PagedCommunitySummaryItem } from "@/types";

/** 社区摘要列表（level 过滤 + 游标分页）。 */
export function listCommunities(
  level?: number,
  cursor?: string,
  limit = 20,
): Promise<PagedCommunitySummaryItem> {
  return http
    .get<PagedCommunitySummaryItem>("/admin/communities", {
      params: { level, cursor, limit },
    })
    .then((r) => r.data);
}
