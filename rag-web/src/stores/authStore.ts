/**
 * authStore（06 §3）：token 与用户态。
 * login 走 POST /auth/token 兑换（02 §3.1）；relogin 供 401 拦截器
 * 静默重兑换（仅 1 次，03 §2.2）。
 */
import { create } from "zustand";

import { issueToken } from "@/api/auth";
import { bindJwt } from "@/lib/agentClient";
import type { AuthTokenRequest, UserInfo } from "@/types";

interface AuthState {
  token: string | null;
  user: UserInfo | null;
  /** 记住最近一次兑换凭证，供 401 静默重兑换使用 */
  lastGrant: AuthTokenRequest | null;
  login(grant: AuthTokenRequest): Promise<void>;
  relogin(): Promise<boolean>;
  logout(): void;
}

export const useAuthStore = create<AuthState>()((set, get) => ({
  token: sessionStorage.getItem("rag_token"),
  user: JSON.parse(sessionStorage.getItem("rag_user") ?? "null") as UserInfo | null,
  lastGrant: null,

  async login(grant) {
    const resp = await issueToken(grant);
    sessionStorage.setItem("rag_token", resp.access_token);
    sessionStorage.setItem("rag_user", JSON.stringify(resp.user));
    bindJwt(resp.access_token); // SDK 直连同源 JWT（J19，06 §5）
    set({ token: resp.access_token, user: resp.user, lastGrant: grant });
  },

  async relogin() {
    const grant = get().lastGrant;
    if (!grant) return false;
    try {
      await get().login(grant);
      return true;
    } catch {
      return false;
    }
  },

  logout() {
    sessionStorage.removeItem("rag_token");
    sessionStorage.removeItem("rag_user");
    set({ token: null, user: null });
  },
}));

// 会话恢复：刷新页面后 sessionStorage token 仍在，重绑 SDK JWT（06 §5）
const _restored = sessionStorage.getItem("rag_token");
if (_restored) bindJwt(_restored);
