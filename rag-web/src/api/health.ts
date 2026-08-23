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
  baseURL: import.meta.env.VITE_API_BASE.replace(/\/api\/v1\/?$/, ""),
  timeout: 10_000,
});

/** 聚合就绪探测（Admin 总览 HealthOverview 数据源）。 */
export function getReady(): Promise<ReadyResponse> {
  return root.get<ReadyResponse>("/ready").then((r) => r.data);
}
