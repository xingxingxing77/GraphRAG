/**
 * useChatStream（06 §6 ★核心 Hook，单元 10.5）：precheck → streamRun →
 * 打字机 全编排（J19/J20/J22）。
 *
 * 三档状态机入口（06 §6.1）：Empty/Prechecking → CacheHit | Streaming →
 * values 终态 → Done/Degraded；M1 铁律：values 到达前中间文本只进
 * ThoughtPanel（由 summarizeNodeUpdate 聚合，服务端不下发聚合字段）。
 * 读超时兜底（03 §7）：fast 10s / standard 30s / deep 55s，超时按
 * CHAT_504_TIER_TIMEOUT 文案展示已收 thought + 重试。
 * precheck 异常按 miss 处理，绝不阻塞主链路（03 §8）。
 */
import { useCallback } from "react";

import { precheck } from "@/api/precheck";
import { bindJwt, ensureThread, streamRun } from "@/lib/agentClient";
import {
  extractFinalState,
  isAgentNode,
  summarizeNodeUpdate,
} from "@/lib/summarize";
import { useAuthStore } from "@/stores/authStore";
import { useChatStore } from "@/stores/chatStore";
import { useSessionStore } from "@/stores/sessionStore";

/** 各档位读超时（03 §7，≥ M3 wall_clock_budget 上限 + 余量）。 */
const TIER_TIMEOUT_MS: Record<"fast" | "standard" | "deep", number> = {
  fast: 10_000,
  standard: 30_000,
  deep: 55_000,
};

/** 错误码 → 文案（06 §9 子集；完整映射随 DegradedBanner/文案表扩展）。 */
export function mapErrorText(code: string): string {
  switch (code) {
    case "CHAT_400_EMPTY_QUERY":
    case "CHAT_400_INVALID_TIER":
      return "输入有误，请检查后重试";
    case "CHAT_429_RATE_LIMITED":
      return "请求太频繁，请稍后再试";
    case "CHAT_504_TIER_TIMEOUT":
      return "回答超时，可重试或切换深度模式";
    case "CHAT_404_THREAD_NOT_FOUND":
      return "会话已失效，请新建会话";
    case "AUTH_401_TOKEN_EXPIRED":
    case "AUTH_401_TOKEN_INVALID":
      return "登录已过期，请重新登录";
    case "SYS_500_INTERNAL":
    case "SYS_503_DEPENDENCY_DOWN":
      return "服务开小差了，请稍后重试";
    default:
      return "请求失败，请稍后重试";
  }
}

/**
 * 聊天流编排 Hook。
 *
 * @returns send 提交一条查询（内部完成 precheck 短路/流消费/终态回写）；
 *          busy 是否编排中。
 */
export function useChatStream() {
  const streaming = useChatStore((s) => s.streaming);

  const send = useCallback(async (query: string, model: string | null = null) => {
    const chat = useChatStore.getState();
    const session = useSessionStore.getState();
    const user = useAuthStore.getState().user;
    if (chat.streaming || !user) return;

    chat.appendUserMessage(query);
    chat.setStreaming(true);

    // 会话标识 = thread_id（GAP-A1：thread_id 即 session 锚点，02 §3.2）；
    // 新会话时为 null（空态），precheck miss 后惰性建 thread 并以 thread_id 承载
    let sessionId: string | null = session.activeSessionId;

    // ① L1 语义缓存短路（J22）：命中直接渲染缓存答案，不发起 run；
    //    miss 时消费 suggested_run.latency_tier（意图启发式建议档位，06 §8.2）
    let suggestedTier: "fast" | "standard" | "deep" | null = null;
    try {
      const pre = await precheck({ query, session_id: sessionId });
      if (pre.hit) {
        chat.appendAssistant({
          content: pre.answer ?? "",
          citations: pre.citations ?? [],
          degraded: false,
          cacheHit: true,
        });
        chat.setStreaming(false);
        return;
      }
      const st = pre.suggested_run?.latency_tier;
      if (st) suggestedTier = st;
    } catch {
      /* precheck 异常按 miss 处理（03 §8） */
    }

    // ② 发起流式 run（线程惰性创建，03 §8）
    try {
      const token = useAuthStore.getState().token;
      if (token) bindJwt(token);
      const threadId = sessionId ?? (await ensureThread(user.id));
      if (!sessionId) {
        sessionId = threadId;
        session.setActive(threadId);
      }

      // 档位优先顺序：suggested_run（precheck 意图启发式）> 用户显式选择 > auto 兜底 standard
      const tier =
        suggestedTier ?? (chat.activeTier === "auto" ? "standard" : chat.activeTier);
      const stream = streamRun(
        threadId,
        { original_query: query, session_id: threadId, user_id: user.id },
        { latency_tier: tier, model: model ?? chat.model ?? null },
      );

      // 读超时兜底（03 §7）：超时中断消费并按 CHAT_504_TIER_TIMEOUT 呈现
      let timedOut = false;
      const timer = setTimeout(() => {
        timedOut = true;
      }, TIER_TIMEOUT_MS[tier]);

      for await (const ev of stream) {
        if (timedOut) break;
        // SDK 1.x 事件为判别联合；此处按字面量归一消费（updates/values/error，03 §3.3）
        const event = String((ev as { event?: unknown }).event ?? "");
        const data = ((ev as { data?: unknown }).data ?? {}) as Record<string, unknown>;
        if (event === "updates") {
          // updates 载荷形如 { "<node>": delta }（03 §3.3，thought 唯一来源）
          const [node, delta] = Object.entries(data)[0] ?? [];
          if (node && isAgentNode(node)) {
            const d = (delta ?? {}) as Record<string, unknown>;
            chat.pushThoughtStep(node, summarizeNodeUpdate(node, d));
            // 重生成提示（5.6）与忠实度徽章（7.1）状态驱动
            if (node === "generator" && d.regenerated === true) chat.setRegenerating(true);
            if (node === "self_correction" && typeof d.faithfulness_score === "number") {
              chat.setFaithfulnessScore(d.faithfulness_score as number);
            }
          }
        } else if (event === "values") {
          const fin = extractFinalState(data);
          chat.setFinalAnswer(fin.answer, fin.citations, fin.degradedReasons);
        } else if (event === "error") {
          const err = (data.error ?? {}) as { code?: string };
          chat.appendAssistant({
            content: `⚠ ${mapErrorText(err.code ?? "SYS_500_INTERNAL")}`,
            degraded: false,
          });
        }
      }
      clearTimeout(timer);
      if (timedOut) {
        chat.appendAssistant({
          content: `⚠ ${mapErrorText("CHAT_504_TIER_TIMEOUT")}`,
          degraded: false,
        });
      }
    } catch (e) {
      const code =
        (e as { response?: { data?: { code?: string } } })?.response?.data?.code ??
        "SYS_500_INTERNAL";
      chat.appendAssistant({ content: `⚠ ${mapErrorText(code)}`, degraded: false });
    } finally {
      chat.setStreaming(false);
    }
  }, []);

  return { send, streaming };
}
