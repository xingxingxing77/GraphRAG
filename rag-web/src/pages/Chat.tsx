/**
 * ChatPage（06 §7 v1.3）：双态主界面。
 * 空态 = EmptyStateHero（"hi GraphRAG" + 建议卡 + 居中大输入框）；
 * 会话态 = 消息流（ThoughtPanel 折叠 + 终态打字机回放，M1）+ 底部停靠
 * 输入条。发送经 useChatStream 全编排（precheck→run→values，单元 10.5）；
 * 左侧 WorkspaceSidebar；顶部 DegradedBanner 常驻。
 */
import { useEffect, useMemo, useState } from "react";

import { DegradedBanner } from "@/components/DegradedBanner";
import { Composer, EmptyStateHero } from "@/components/EmptyStateHero";
import { FaithfulnessBadge } from "@/components/FaithfulnessBadge";
import { FeedbackButtons } from "@/components/FeedbackButtons";
import { MarkdownAnswer } from "@/components/MarkdownAnswer";
import { RegenerationNotice } from "@/components/RegenerationNotice";
import { WorkspaceSidebar } from "@/components/WorkspaceSidebar";
import { deleteSession } from "@/api/sessions";
import { useChatStream } from "@/hooks/useChatStream";
import { useTypewriter } from "@/hooks/useTypewriter";
import { useChatStore } from "@/stores/chatStore";
import { useSessionStore } from "@/stores/sessionStore";
import type { ChatMessage } from "@/stores/chatStore";

/** 终态打字机气泡（M1：values 到达后回放；skip=立即显示全部，无障碍）。 */
function TypewriterMessage({ text }: { text: string }) {
  const consume = useChatStore((s) => s.consumeTypewriter);
  const { shown, done, skip } = useTypewriter(text);
  useEffect(() => {
    if (done) consume();
  }, [done, consume]);
  return (
    <span>
      {shown}
      {!done ? (
        <button
          className="ml-2 align-middle text-[11px] text-neutral-400 underline hover:text-neutral-600"
          onClick={skip}
        >
          立即显示全部
        </button>
      ) : null}
    </span>
  );
}

export default function ChatPage() {
  const messages = useChatStore((s) => s.messages);
  const thoughtSteps = useChatStore((s) => s.thoughtSteps);
  const streaming = useChatStore((s) => s.streaming);
  const typewriterTarget = useChatStore((s) => s.typewriterTarget);
  const regenerating = useChatStore((s) => s.regenerating);
  const faithfulnessScore = useChatStore((s) => s.faithfulnessScore);
  const loadHistory = useChatStore((s) => s.loadHistory);
  const reset = useChatStore((s) => s.reset);

  const { send } = useChatStream();

  const sessions = useSessionStore((s) => s.sessions);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const setActive = useSessionStore((s) => s.setActive);
  const loadMore = useSessionStore((s) => s.loadMore);
  const remove = useSessionStore((s) => s.remove);

  /** 侧栏搜索过滤词（前端过滤 title，02 契约零变更） */
  const [search, setSearch] = useState("");

  useEffect(() => {
    void loadMore(true);
  }, [loadMore]);

  /** 侧栏过滤后的会话列表（标题包含，大小写不敏感）。 */
  const filteredSessions = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => (s.title ?? "").toLowerCase().includes(q));
  }, [sessions, search]);

  /** 删除会话：API 204（失败静默，后端未就绪时仅本地移除）。 */
  function handleDelete(sessionId: string) {
    void deleteSession(sessionId).catch(() => undefined);
    remove(sessionId);
  }

  /** 选择会话：装载历史消息（10.8 批次 B：会话历史装载，02 §3.3）。 */
  function handleSelect(sessionId: string) {
    setActive(sessionId);
    void loadHistory(sessionId);
  }

  /** 新建会话：清空消息态（回到空态）。 */
  function handleNew() {
    setActive(null);
    reset();
  }

  /** 气泡渲染（终态打字机：typewriterTarget 与该条内容一致时回放）。 */
  function renderBubble(m: ChatMessage, isLast: boolean) {
    const typing = m.role === "assistant" && typewriterTarget !== null && typewriterTarget === m.content;
    return (
      <div className="inline-block max-w-[80%] rounded-2xl border border-neutral-200 px-3.5 py-2 text-left text-sm dark:border-neutral-700">
        {m.role === "assistant" ? (
          typing ? (
            <TypewriterMessage text={m.content} />
          ) : (
            <MarkdownAnswer content={m.content} citations={m.citations} />
          )
        ) : (
          m.content
        )}
        <span className="mt-1 flex flex-wrap items-center gap-1">
          {m.cacheHit ? (
            <span className="rounded-full bg-neutral-100 px-1.5 py-0.5 text-[10px] text-neutral-500 dark:bg-neutral-800">
              缓存命中
            </span>
          ) : null}
          {m.degraded ? (
            <span className="rounded-full bg-orange-100 px-1.5 py-0.5 text-[10px] text-orange-600 dark:bg-orange-950 dark:text-orange-300">
              已降级
            </span>
          ) : null}
          {m.role === "assistant" && isLast && faithfulnessScore !== null ? (
            <FaithfulnessBadge score={faithfulnessScore} />
          ) : null}
          {m.role === "assistant" && isLast ? <RegenerationNotice visible={regenerating} /> : null}
        </span>
        {m.role === "assistant" ? <FeedbackButtons messageId={m.messageId ?? m.id} /> : null}
      </div>
    );
  }

  return (
    <div className="flex h-screen">
      <WorkspaceSidebar
        sessions={filteredSessions}
        activeId={activeSessionId}
        onSelect={handleSelect}
        onNew={handleNew}
        onDelete={handleDelete}
        onSearch={setSearch}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <DegradedBanner />
        {messages.length === 0 ? (
          <EmptyStateHero suggestions={[]} onSubmit={(q) => void send(q)} />
        ) : (
          <>
            <div className="flex-1 space-y-3 overflow-y-auto px-6 py-4">
              {messages.map((m, idx) => (
                <div key={m.id} className={m.role === "user" ? "text-right" : ""}>
                  {renderBubble(m, idx === messages.length - 1)}
                </div>
              ))}
              {/* ThoughtPanel（03 §3.5 前端聚合；M1：中间产物只进折叠区） */}
              {thoughtSteps.length > 0 ? (
                <details
                  open={streaming}
                  className="mx-auto max-w-3xl rounded-xl border border-neutral-200 px-3 py-2 text-xs text-neutral-500 dark:border-neutral-700"
                >
                  <summary className="cursor-pointer select-none">
                    思考过程（{thoughtSteps.length}）
                  </summary>
                  <ol className="mt-1.5 space-y-1">
                    {thoughtSteps.map((t, i) => (
                      <li key={`${t.node}_${i}`}>
                        <span className="mr-1.5 rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-[10px] dark:bg-neutral-800">
                          {t.node}
                        </span>
                        {t.summary}
                      </li>
                    ))}
                  </ol>
                </details>
              ) : null}
            </div>
            <footer className="px-6 pb-5">
              <div className="mx-auto max-w-3xl">
                <Composer compact onSubmit={(q) => void send(q)} />
                {streaming ? (
                  <p className="mt-1.5 text-center text-[11px] text-neutral-400">思考中…</p>
                ) : null}
              </div>
            </footer>
          </>
        )}
      </main>
    </div>
  );
}
