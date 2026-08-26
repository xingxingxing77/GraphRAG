/**
 * MessageBubble（06 §8 · 批次 C BUI 业务包装）：消息气泡。
 * BUI 视觉（streaming-text 落点）：assistant 用 surface 卡 + line 描边 + ink 正文，
 * user 用 field 软块；终态打字机回放内嵌流式光标（M1）；
 * 引用经 MarkdownAnswer 内联 [n] 角标；缓存/降级/复核徽章与反馈按钮同泡。
 */
import { useEffect } from "react";

import { FaithfulnessBadge } from "@/components/FaithfulnessBadge";
import { FeedbackButtons } from "@/components/FeedbackButtons";
import { MarkdownAnswer } from "@/components/MarkdownAnswer";
import { RegenerationNotice } from "@/components/RegenerationNotice";
import { useTypewriter } from "@/hooks/useTypewriter";
import { useChatStore, type ChatMessage } from "@/stores/chatStore";

/** 终态打字机回放（M1）：BUI 流式光标 + 无障碍「立即显示全部」。 */
function TypewriterText({ text }: { text: string }) {
  const consume = useChatStore((s) => s.consumeTypewriter);
  const { shown, done, skip } = useTypewriter(text);
  useEffect(() => {
    if (done) consume();
  }, [done, consume]);
  return (
    <span>
      {shown}
      {!done ? (
        <span className="ml-0.5 inline-block h-3 w-0.5 translate-y-0.5 rounded-full bg-ink" />
      ) : null}
      {!done ? (
        <button
          className="ml-2 align-middle text-[11px] text-ink-3 underline hover:text-ink-2"
          onClick={skip}
        >
          立即显示全部
        </button>
      ) : null}
    </span>
  );
}

/** 用户 / 助手双侧气泡。 */
export function MessageBubble({ msg, isLast }: { msg: ChatMessage; isLast: boolean }) {
  const typewriterTarget = useChatStore((s) => s.typewriterTarget);
  const regenerating = useChatStore((s) => s.regenerating);
  const faithfulnessScore = useChatStore((s) => s.faithfulnessScore);
  const typing =
    msg.role === "assistant" && typewriterTarget !== null && typewriterTarget === msg.content;

  return (
    <div className={msg.role === "user" ? "flex justify-end" : "flex justify-start"}>
      <div
        className={
          msg.role === "user"
            ? "max-w-[80%] rounded-card bg-field px-3.5 py-2 text-left text-[13px] leading-relaxed text-ink"
            : "max-w-[80%] rounded-card border border-line bg-surface px-4 py-2.5 text-left text-[13px] leading-relaxed text-ink shadow-card"
        }
      >
        {msg.role === "assistant" ? (
          typing ? (
            <TypewriterText text={msg.content} />
          ) : (
            <MarkdownAnswer content={msg.content} citations={msg.citations} />
          )
        ) : (
          msg.content
        )}

        {msg.role === "assistant" ? (
          <span className="mt-1 flex flex-wrap items-center gap-1">
            {msg.cacheHit ? (
              <span className="rounded-chip bg-inset px-2 py-0.5 text-[10px] text-ink-2">缓存命中</span>
            ) : null}
            {msg.degraded ? (
              <span className="rounded-chip bg-red-tint px-2 py-0.5 text-[10px] text-red">已降级</span>
            ) : null}
            {isLast && faithfulnessScore !== null ? (
              <FaithfulnessBadge score={faithfulnessScore} />
            ) : null}
            {isLast ? <RegenerationNotice visible={regenerating} /> : null}
          </span>
        ) : null}

        {msg.role === "assistant" ? <FeedbackButtons messageId={msg.messageId ?? msg.id} /> : null}
      </div>
    </div>
  );
}
