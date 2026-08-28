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
  extractMessageChunk,
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

/** 错误码 → 文案（06 §9 / 02 §6；校验类统一为“输入有误”，服务端故障为“开小差”）。 */
export function mapErrorText(code: string): string {
  switch (code) {
    case "CHAT_400_EMPTY_QUERY":
    case "CHAT_400_INVALID_TIER":
    case "SYS_400_VALIDATION":
    case "SYS_404_NOT_FOUND":
    case "DEBUG_400_INVALID_SOURCE":
      return "输入有误，请检查后重试";
    case "CHAT_429_RATE_LIMITED":
      return "请求太频繁，请稍后再试";
    case "CHAT_504_TIER_TIMEOUT":
      return "回答超时，可重试或切换深度模式";
    case "CHAT_404_THREAD_NOT_FOUND":
    case "SESSION_404_NOT_FOUND":
      return "会话已失效，请新建会话";
    case "AUTH_401_TOKEN_EXPIRED":
    case "AUTH_401_TOKEN_INVALID":
      return "登录已过期，请重新登录";
    case "SYS_500_INTERNAL":
    case "SYS_503_DEPENDENCY_DOWN":
    case "GRAPH_503_STORE_UNAVAILABLE":
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

    // 前置输入校验：空/空白/超长直接本地拦截，避免走到服务端 400/500 再误判为“开小差”
    const trimmed = query.trim();
    if (!trimmed) {
      chat.appendAssistant({ content: `⚠ ${mapErrorText("CHAT_400_EMPTY_QUERY")}`, degraded: false });
      return;
    }
    if (trimmed.length > 2000) {
      chat.appendAssistant({ content: `⚠ ${mapErrorText("SYS_400_VALIDATION")}`, degraded: false });
      return;
    }
    // 统一用 trim 后的正文进入链路（避免 "   " 穿透到后端）
    const normalizedQuery = trimmed;

    chat.appendUserMessage(normalizedQuery);
    // P0-07/P1: 每轮重置 thought/降级态，避免跨轮堆积（S-04, Z-03）
    chat.clearThoughts();
    chat.setRegenerating(false);
    chat.setFaithfulnessScore(null as unknown as number);
    chat.clearDegraded();
    chat.setStreaming(true);

    // 会话标识 = thread_id（GAP-A1：thread_id 即 session 锚点，02 §3.2）；
    // 新会话时为 null（空态），precheck miss 后惰性建 thread 并以 thread_id 承载
    let sessionId: string | null = session.activeSessionId;

    // ① L1 语义缓存短路（J22）：命中直接渲染缓存答案，不发起 run；
    //    miss 时消费 suggested_run.latency_tier（意图启发式建议档位，06 §8.2）
    let suggestedTier: "fast" | "standard" | "deep" | null = null;
    try {
      const pre = await precheck({ query: normalizedQuery, session_id: sessionId });
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
    } catch (e) {
      // 400 校验类错误直接透出“输入有误”，其他按 miss 处理（03 §8）
      const preCode = (e as { response?: { data?: { code?: string } } })?.response?.data?.code ?? "";
      if (preCode === "CHAT_400_EMPTY_QUERY" || preCode === "SYS_400_VALIDATION") {
        chat.appendAssistant({ content: `⚠ ${mapErrorText(preCode)}`, degraded: false });
        chat.setStreaming(false);
        return;
      }
      /* 其他 precheck 异常按 miss 处理 */
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
      // C6：latency_tier/model 属 run 入参契约（ChatRunInput）——
      // 经 config.configurable 传入时图内无人读取，选择会被静默忽略
      const stream = streamRun(threadId, {
        original_query: normalizedQuery,
        session_id: threadId,
        user_id: user.id,
        latency_tier: tier,
        model: model ?? chat.model ?? null,
      });

      // 读超时兜底（03 §7）：按「无事件间隔」计时（每收到事件重置），
      // 绝对时长会在 fast 档正常流式或慢依赖场景误报
      let timedOut = false;
      let timer: ReturnType<typeof setTimeout> | null = setTimeout(() => {
        timedOut = true;
      }, TIER_TIMEOUT_MS[tier]);

      const clearTimer = () => {
        if (timer) {
          clearTimeout(timer);
          timer = null;
        }
      };
      const resetTimer = () => {
        clearTimer();
        timer = setTimeout(() => {
          timedOut = true;
        }, TIER_TIMEOUT_MS[tier]);
      };

      try {
        for await (const ev of stream) {
          if (timedOut) break;
          resetTimer();
          // SDK 1.x 事件为判别联合；兼容 ev.event 与 ev.data.event（P0-07 S-05）
          const raw = ev as unknown as Record<string, unknown>;
          const event =
            String((raw.event as string | undefined) ?? "") ||
            String(((raw.data as Record<string, unknown> | undefined)?.event as string | undefined) ?? "") ||
            // fallback: 若 ev 本身形如 {updates: {...}} 则视为 updates
            (raw.updates || raw.values ? String(Object.keys(raw)[0] ?? "") : "");
          // data 兼容两层嵌套
          const maybeData = (raw.data as Record<string, unknown> | undefined) ?? raw;
          const data = (maybeData.data as Record<string, unknown> | undefined) ?? maybeData;

          if (event === "updates" || raw.updates) {
            // updates 载荷形如 { "<node>": delta }，可能多 key 批量（P0-07 S-03）
            const updatesPayload =
              (data.updates as Record<string, unknown> | undefined) ??
              (raw.updates as Record<string, unknown> | undefined) ??
              data;
            for (const [node, delta] of Object.entries(updatesPayload)) {
              if (!node || node === "event" || node === "data") continue;
              if (!isAgentNode(node)) continue;
              const d = (delta ?? {}) as Record<string, unknown>;
              chat.pushThoughtStep(node, summarizeNodeUpdate(node, d));
              if (node === "generator" && d.regenerated === true) chat.setRegenerating(true);
              if (node === "self_correction" && typeof d.faithfulness_score === "number") {
                chat.setFaithfulnessScore(d.faithfulness_score as number);
              }
            }
          } else if (event === "values" || raw.values) {
            const valuesPayload =
              (data.values as Record<string, unknown> | undefined) ??
              (raw.values as Record<string, unknown> | undefined) ??
              data;
            const fin = extractFinalState(valuesPayload as Record<string, unknown>);
            // m11：values 终态的实际档位回写消息（03 §3.6 契约）
            chat.setFinalAnswer(fin.answer, fin.citations, fin.degradedReasons, fin.latencyTier);
          } else if (event === "error") {
            const err = (data.error ?? {}) as { code?: string };
            chat.appendAssistant({
              content: `⚠ ${mapErrorText(err.code ?? "SYS_500_INTERNAL")}`,
              degraded: false,
            });
          } else if (event.startsWith("messages")) {
            // messages-tuple 事件（含 v2 别名 messages/partial 等）。
            // J8/M1：仅 fast 档逐 token 直推；standard/deep 缓冲式，
            // 中间 token 不出折叠面板，由 values 终态统一落地
            if (tier !== "fast") continue;
            const chunk = extractMessageChunk((raw.data as unknown) ?? ev);
            if (chunk) chat.appendStreamChunk(chunk);
          }
        }
      } finally {
        clearTimer();
      }
      if (timedOut) {
        chat.appendAssistant({
          content: `⚠ ${mapErrorText("CHAT_504_TIER_TIMEOUT")}`,
          degraded: false,
        });
      }
    } catch (e) {
      const ax = e as {
        response?: { data?: { code?: string; message?: string } ; status?: number };
        code?: string;
        message?: string;
      };
      const rawCode = ax?.response?.data?.code ?? ax?.code ?? "";
      // 兜底：若 code 缺失但 status 为 400/404，按校验类映射，避免“开小差”误导
      let code = rawCode || "SYS_500_INTERNAL";
      if (!rawCode) {
        const status = ax?.response?.status;
        if (status === 400) code = "SYS_400_VALIDATION";
        else if (status === 404) code = "SYS_404_NOT_FOUND";
      }
      // 额外透出原始 message 到控制台，便于排查输入问题时不丢失上下文
      if (typeof console !== "undefined" && console.debug) {
        console.debug("[useChatStream] run failed", { code, raw: ax?.response?.data ?? ax });
      }
      chat.appendAssistant({ content: `⚠ ${mapErrorText(code)}`, degraded: false });
    } finally {
      chat.setStreaming(false);
    }
  }, []);

  return { send, streaming };
}
