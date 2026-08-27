/**
 * 模型清单 Hook（14 §BUG-PB-02 修复）。
 *
 * 数据源：`PublicConfig.models: ModelOption[]`（`src/types/api.ts:1546-1558`），
 * 通过 `GET /config/public` 拉取。该端点是 J2「请求参数指定模型」的前端前提，
 * 由 `src/api/config.ts:getPublicConfig()` 封装。
 *
 * 缓存策略：内存 5 分钟 TTL，跨组件共享。失败时回退占位 `Default`，不阻塞 UI。
 */

import { useEffect, useState } from "react";

import { getPublicConfig } from "@/api/config";
import type { ModelOption } from "@/types";

const CACHE_TTL_MS = 5 * 60 * 1000;

let cached: { fetchedAt: number; models: ModelOption[] } | null = null;
let inflight: Promise<ModelOption[]> | null = null;

const FALLBACK: ModelOption[] = [
  { id: "default", label: "Default", provider: "local" },
];

async function fetchModels(): Promise<ModelOption[]> {
  if (cached && Date.now() - cached.fetchedAt < CACHE_TTL_MS) {
    return cached.models;
  }
  if (inflight) return inflight;

  inflight = (async () => {
    try {
      const cfg = await getPublicConfig();
      const list = (cfg.models ?? []).filter((m): m is ModelOption => Boolean(m && m.id));
      cached = { fetchedAt: Date.now(), models: list };
      return list;
    } catch (err) {
      console.warn("[useModels] getPublicConfig failed, using fallback", err);
      return FALLBACK;
    } finally {
      inflight = null;
    }
  })();

  return inflight;
}

export function useModels(): ModelOption[] {
  const [models, setModels] = useState<ModelOption[]>(cached?.models ?? FALLBACK);

  useEffect(() => {
    let cancelled = false;
    fetchModels().then((list) => {
      if (!cancelled) setModels(list);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return models;
}

/** 非 React 上下文获取最新模型清单 */
export async function getModels(): Promise<ModelOption[]> {
  return fetchModels();
}
