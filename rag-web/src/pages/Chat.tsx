/**
 * ChatPage（06 §7 v1.3）：双态主界面。
 * 空态 = EmptyStateHero（"hi GraphRAG" + 建议卡 + 居中大输入框）；
 * 会话态 = 消息流（MessageBubble + ThoughtPanel）+ 底部停靠输入条。
 * 发送经 useChatStream 全编排（precheck→run→values，单元 10.5）；
 * 批次 C：气泡 / 思考面板 / 输入区已 BUI 业务包装（06 §10.4）。
 */
import { useEffect, useMemo, useState } from "react";

import { DegradedBanner } from "@/components/DegradedBanner";
import { Composer, EmptyStateHero } from "@/components/EmptyStateHero";
import { MessageBubble } from "@/components/MessageBubble";
import { ThoughtPanel } from "@/components/ThoughtPanel";
import { WorkspaceSidebar } from "@/components/WorkspaceSidebar";
import { deleteSession } from "@/api/sessions";
import { useChatStream } from "@/hooks/useChatStream";
import { useChatStore } from "@/stores/chatStore";
import { useSessionStore } from "@/stores/sessionStore";

export default function ChatPage() {
  const messages = useChatStore((s) => s.messages);
  const thoughtSteps = useChatStore((s) => s.thoughtSteps);
  const streaming = useChatStore((s) => s.streaming);
  const loadHistory = useChatStore((s) => s.loadHistory);
  const reset = useChatStore((s) => s.reset);

  const { send } = useChatStream();

  const sessions = useSessionStore((s) => s.sessions);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const setActive = useSessionStore((s) => s.setActive);
  const loadMore = useSessionStore((s) => s.loadMore);
  const remove = useSessionStore((s) => s.remove);

  /** 侧栏搜索过滤词（前端过滤 title，02 契约零变更）。 */
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
                <MessageBubble key={m.id} msg={m} isLast={idx === messages.length - 1} />
              ))}
              {/* ThoughtPanel（03 §3.5 前端聚合；M1：中间产物只进折叠区） */}
              {thoughtSteps.length > 0 ? (
                <ThoughtPanel steps={thoughtSteps} streaming={streaming} />
              ) : null}
            </div>
            <footer className="px-6 pb-5">
              <div className="mx-auto max-w-3xl">
                <Composer compact onSubmit={(q) => void send(q)} />
                {streaming ? (
                  <p className="mt-1.5 text-center text-[11px] text-ink-3">思考中…</p>
                ) : null}
              </div>
            </footer>
          </>
        )}
      </main>
    </div>
  );
}
