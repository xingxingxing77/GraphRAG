/**
 * ChatPage（06 §7 v1.3）：双态主界面。
 * 空态 = EmptyStateHero（"hi GraphRAG" + 建议卡 + 居中大输入框）；
 * 会话态 = 消息流 + 底部停靠输入条（Composer compact，双态同构）。
 * 左侧 WorkspaceSidebar（时间分组树/搜索/导航/设置）；顶部 DegradedBanner
 * 常驻。发送编排 useChatStream（precheck→stream→打字机）随单元 10.3-10.5
 * 接入，当前为布局骨架（占位应答）。
 */
import { useEffect, useMemo, useState } from "react";

import { DegradedBanner } from "@/components/DegradedBanner";
import { Composer, EmptyStateHero } from "@/components/EmptyStateHero";
import { WorkspaceSidebar } from "@/components/WorkspaceSidebar";
import { deleteSession } from "@/api/sessions";
import { useChatStore } from "@/stores/chatStore";
import { useSessionStore } from "@/stores/sessionStore";

export default function ChatPage() {
  const messages = useChatStore((s) => s.messages);
  const appendUserMessage = useChatStore((s) => s.appendUserMessage);
  const appendAssistant = useChatStore((s) => s.appendAssistant);

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

  /**
   * 发送编排（骨架版）：落用户消息 + 占位应答。
   * TODO(10.3-10.5): 替换为 useChatStream 全编排（precheck→run→打字机）。
   */
  function send(query: string) {
    appendUserMessage(query);
    appendAssistant({
      content: "（链路占位）useChatStream 编排随单元 10.3-10.5 接入。",
    });
  }

  /** 删除会话：API 204（失败静默，后端未就绪时仅本地移除）。 */
  function handleDelete(sessionId: string) {
    void deleteSession(sessionId).catch(() => undefined);
    remove(sessionId);
  }

  return (
    <div className="flex h-screen">
      <WorkspaceSidebar
        sessions={filteredSessions}
        activeId={activeSessionId}
        onSelect={(id) => setActive(id)}
        onNew={() => setActive(null)}
        onDelete={handleDelete}
        onSearch={setSearch}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <DegradedBanner />
        {messages.length === 0 ? (
          <EmptyStateHero suggestions={[]} onSubmit={send} />
        ) : (
          <>
            <div className="flex-1 space-y-3 overflow-y-auto px-6 py-4">
              {messages.map((m) => (
                <div key={m.id} className={m.role === "user" ? "text-right" : ""}>
                  <span className="inline-block max-w-[80%] rounded-2xl border border-neutral-200 px-3.5 py-2 text-left text-sm dark:border-neutral-700">
                    {m.content}
                  </span>
                  {/* 消息气泡 latency_tier 徽章（6.2：实际执行档位） */}
                  {m.role === "assistant" && m.latencyTier ? (
                    <span className="ml-2 inline-block rounded-full bg-neutral-100 px-2 py-0.5 align-middle text-[10px] text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400">
                      {m.latencyTier}
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
            <footer className="px-6 pb-5">
              <div className="mx-auto max-w-3xl">
                <Composer compact onSubmit={send} />
              </div>
            </footer>
          </>
        )}
      </main>
    </div>
  );
}
