/**
 * 图谱代理端点封装（02 §3.6）。
 */
import { http } from "./http";

import type { SubgraphResponse } from "@/types";

/** 按实体查询可视化子图（NVL 直连格式）。 */
export function getSubgraph(
  entity: string,
  depth = 2,
  limit = 50,
): Promise<SubgraphResponse> {
  return http
    .get<SubgraphResponse>("/graph/subgraph", { params: { entity, depth, limit } })
    .then((r) => r.data);
}
