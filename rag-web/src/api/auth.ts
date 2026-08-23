/**
 * 认证端点封装（02 §3.1 POST /auth/token）。
 */
import { http } from "./http";

import type { AuthTokenRequest, TokenResponse } from "@/types";

/** 兑换 JWT（api_key 或 password 二选一凭证）。 */
export function issueToken(body: AuthTokenRequest): Promise<TokenResponse> {
  return http.post<TokenResponse>("/auth/token", body).then((r) => r.data);
}
