/**
 * Agent 面 SDK 封装（06 §5，全站唯一入口）。
 * 直连 langgraph-server :8001（J19）；custom auth 校验与业务面同源 JWT。
 */
import { Client } from "@langchain/langgraph-sdk";

import type { ChatRunInput, RunConfigurable } from "@/types";

let _jwt: string | null = sessionStorage.getItem("rag_token");

function _headers(): Record<string, string> {
  return _jwt ? { Authorization: `Bearer ${_jwt}` } : {};
}

export const client = new Client({
  apiUrl: import.meta.env.VITE_AGENT_BASE,
  defaultHeaders: _headers(),
  fetch: ((input: RequestInfo | URL, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    if (_jwt && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${_jwt}`);
    return fetch(input, { ...init, headers });
  }) as unknown as typeof fetch,
} as unknown as ConstructorParameters<typeof Client>[0]);

/** 绑定 JWT（与业务面同源 token，03 §2.1）。 */
export function bindJwt(token: string): void {
  _jwt = token;
  // 兼容旧 SDK 字段（若存在）
  try {
    (client as unknown as Record<string, unknown>).apiKey = token;
  } catch {
    /* ignore */
  }
}

// 线程创建去重（P0-07 S-08）：并发 ensureThread 合并为一次
let _threadPromise: Promise<string> | null = null;

/** 创建 thread（GAP-A1：带 user_id metadata，thread_id 即 session 锚点）。 */
export async function ensureThread(userId: string): Promise<string> {
  if (_threadPromise) return _threadPromise;
  _threadPromise = client.threads
    .create({ metadata: { user_id: userId } })
    .then((th) => th.thread_id)
    .finally(() => {
      _threadPromise = null;
    });
  return _threadPromise;
}

/** 发起流式 run（streamMode 见 03 §3.3；fast 档由后端追加 messages）。 */
export function streamRun(threadId: string, input: ChatRunInput, cfg: RunConfigurable) {
  const payload = {
    input: { ...input },
    config: { configurable: { ...cfg } },
    streamMode: ["updates", "messages-tuple"] as ("updates" | "messages-tuple")[],
    multitaskStrategy: "interrupt" as const,
  };
  // 显式透传 headers 以兼容 custom auth（P0-07）
  const headers = _headers();
  return client.runs.stream(
    threadId,
    import.meta.env.VITE_AGENT_ASSISTANT,
    payload as unknown as Record<string, unknown> & { headers?: Record<string, string> },
    // @ts-expect-error SDK 未声明 headers 透传，运行时 fetch 会合并
    { headers } as unknown as undefined,
  );
}

export { _jwt };
