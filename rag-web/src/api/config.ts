/**
 * 公共配置端点封装（02 §3.7 GET /config/public）。
 */
import { http } from "./http";

import type { PublicConfig } from "@/types";

/** 拉取可选模型条目 + 档位/压缩策略枚举 + Profile。 */
export function getPublicConfig(): Promise<PublicConfig> {
  return http.get<PublicConfig>("/config/public").then((r) => r.data);
}
