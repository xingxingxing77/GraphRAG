/**
 * axios 实例与拦截器（06 §4）。
 *
 * 全站唯一 REST 出口（06 §2：仅 src/api/ 允许 fetch REST）：
 * - 请求注入 Authorization: Bearer <jwt>
 * - 响应采集 X-Degraded 头写入全局降级状态（03 §5）
 * - 401 静默重兑换一次（03 §2.2），失败清 authStore 并跳 /login
 */
import axios from "axios";

import { useAuthStore } from "@/stores/authStore";
import { useChatStore } from "@/stores/chatStore";

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE,
  timeout: 10_000,
});

http.interceptors.request.use((cfg) => {
  const t = useAuthStore.getState().token;
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

let relogining = false;
http.interceptors.response.use(
  (res) => {
    const deg = res.headers["x-degraded"] as string | undefined;
    if (deg) useChatStore.getState().pushDegraded(deg.split(","));
    return res;
  },
  async (err) => {
    if (axios.isAxiosError(err) && err.response?.status === 401 && !relogining) {
      relogining = true;
      const ok = await useAuthStore.getState().relogin();
      relogining = false;
      if (ok && err.config) return http(err.config);
      useAuthStore.getState().logout();
      window.location.href = "/login";
    }
    return Promise.reject(err);
  },
);
