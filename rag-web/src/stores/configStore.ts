/**
 * configStore（06 §3）：启动时拉 GET /config/public 缓存枚举
 * （02 §3.7；单元 0.4 S2 对接，后端未就绪时以 stub 先行）。
 */
import { create } from "zustand";

import type { ModelOption } from "@/types";

interface ConfigState {
  models: ModelOption[];
  latencyTiers: string[];
  compressionStrategies: string[];
  profile: string;
  loaded: boolean;
  load(): Promise<void>;
}

export const useConfigStore = create<ConfigState>()((set) => ({
  models: [],
  latencyTiers: ["fast", "standard", "deep"],
  compressionStrategies: ["llm_extract", "extractive", "none"],
  profile: "cloud-primary",
  loaded: false,

  async load() {
    // 动态 import 避免与 http 拦截器的 store 循环依赖在模块初始化期触发
    const { getPublicConfig } = await import("@/api/config");
    try {
      const cfg = await getPublicConfig();
      set({
        models: cfg.models,
        latencyTiers: cfg.latency_tiers,
        compressionStrategies: cfg.compression_strategies,
        profile: cfg.profile,
        loaded: true,
      });
    } catch {
      // 后端未就绪：保留 stub 枚举（0.4 S2 约定），不阻塞前端启动
      set({ loaded: false });
    }
  },
}));
