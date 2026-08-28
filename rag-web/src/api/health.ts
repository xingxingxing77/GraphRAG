/**
 * 健康端点封装（02 §3.9）。
 * /health 与 /ready 挂在服务根路径（无 /api/v1 前缀），
 * 故独立 axios 实例从 VITE_API_BASE 派生根地址（仅此目录允许 REST，06 §2）。
 */
import axios from "axios";

/** 单组件健康状态（status ∈ up|degraded|down，02 §3.9）。 */
export interface HealthComponent {
  status: "up" | "degraded" | "down";
  latency_ms?: number;
  detail?: string;
}

/** GET /ready 响应（七组件聚合）。 */
export interface ReadyResponse {
  status: string;
  components: Record<string, HealthComponent>;
}

/** 根地址实例（VITE_API_BASE 形如 http://host:8000/api/v1）。 */
const root = axios.create({
  baseURL: (import.meta.env.VITE_API_BASE ?? "").replace(/\/api\/v1\/?$/, ""),
  timeout: 10_000,
});

root.interceptors.response.use((res) => {
  const h = res.headers as Record<string, unknown>;
  const deg = (h["x-degraded"] as string | undefined) ?? (h["X-Degraded"] as string | undefined);
  if (deg) {
    // 动态导入避免循环
    import("@/stores/chatStore").then(({ useChatStore }) => {
      useChatStore.getState().pushDegraded(deg.split(","));
    });
  }
  return res;
});

/** 聚合就绪探测（Admin 总览 HealthOverview 数据源）。
 *
 * m2：critical 依赖 down 时后端仍返回完整聚合体（仅状态码 503）——
 * 503 必须视为有效响应，恰恰是故障时最需要看到七组件状态。
 */
export function getReady(): Promise<ReadyResponse> {
  return root
    .get<ReadyResponse>("/ready", {
      validateStatus: (s) => s === 200 || s === 503,
    })
    .then((r) => r.data);
}
