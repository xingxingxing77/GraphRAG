/**
 * Agent 面 SDK 封装（06 §5，全站唯一入口）。
 * 直连 langgraph-server :8001（J19）；custom auth 校验与业务面同源 JWT。
 */
import { Client } from "@langchain/langgraph-sdk";

import type { ChatRunInput, RunConfigurable } from "@/types";

const client = new Client({ apiUrl: import.meta.env.VITE_AGENT_BASE });

/** 绑定 JWT（与业务面同源 token，03 §2.1）。 */
export function bindJwt(token: string): void {
  // SDK 请求头注入；langgraph-sdk Client 构造后通过自定义 caller 覆写
  (client as unknown as { apiKey?: string }).apiKey = token;
}

/** 创建 thread（GAP-A1：带 user_id metadata，thread_id 即 session 锚点）。 */
export async function ensureThread(userId: string): Promise<string> {
  const th = await client.threads.create({ metadata: { user_id: userId } });
  return th.thread_id;
}

/** 发起流式 run（streamMode 见 03 §3.3；fast 档由后端追加 messages）。 */
export function streamRun(threadId: string, input: ChatRunInput, cfg: RunConfigurable) {
  const payload = {
    input: { ...input },
    config: { configurable: { ...cfg } },
    streamMode: ["updates", "messages-tuple"] as ("updates" | "messages-tuple")[],
    multitaskStrategy: "interrupt" as const,
  };
  return client.runs.stream(threadId, import.meta.env.VITE_AGENT_ASSISTANT, payload);
}

export { client };
