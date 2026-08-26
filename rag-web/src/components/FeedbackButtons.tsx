/**
 * FeedbackButtons（06 §8）：up/down → POST /feedback（02 §3.5）。
 * down 必选 reason + 可选 comment；点踩进 bad case 队列（D8 回流）。
 */
import { useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";

import { submitFeedback } from "@/api/feedback";
import { useSessionStore } from "@/stores/sessionStore";
import type { FeedbackRequest } from "@/types";

const REASONS: { value: NonNullable<FeedbackRequest["reason"]>; label: string }[] = [
  { value: "wrong", label: "答案错误" },
  { value: "incomplete", label: "回答不完整" },
  { value: "unsafe", label: "不安全内容" },
  { value: "other", label: "其他" },
];

const BASE_BTN =
  "flex h-7 w-7 items-center justify-center rounded-control border transition-colors ";

export function FeedbackButtons({ messageId }: { messageId: string }) {
  const sessionId = useSessionStore((s) => s.activeSessionId);
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const [picking, setPicking] = useState(false);
  const [reason, setReason] = useState<NonNullable<FeedbackRequest["reason"]> | null>(null);
  const [comment, setComment] = useState("");

  async function send(r: "up" | "down") {
    if (r === "down" && !reason) {
      setRating("down");
      setPicking(true);
      return;
    }
    await submitFeedback({
      session_id: sessionId ?? "",
      message_id: messageId,
      rating: r,
      reason: r === "down" ? reason : null,
      comment: comment.trim() || null,
    }).catch(() => undefined);
    setRating(r);
    setPicking(false);
    setComment("");
  }

  const upCls =
    BASE_BTN +
    (rating === "up"
      ? "border-green bg-green-tint text-green"
      : "border-line text-ink-3 hover:border-line-strong hover:text-ink");
  const downCls =
    BASE_BTN +
    (rating === "down"
      ? "border-red bg-red-tint text-red"
      : "border-line text-ink-3 hover:border-line-strong hover:text-ink");

  return (
    <div className="mt-1.5 flex items-center gap-1.5">
      <button className={upCls} onClick={() => void send("up")} aria-label="点赞" title="有用">
        <ThumbsUp size={13} />
      </button>
      <button className={downCls} onClick={() => void send("down")} aria-label="点踩" title="点踩（需选原因）">
        <ThumbsDown size={13} />
      </button>
      {picking ? (
        <div className="ml-1 flex flex-wrap items-center gap-1.5 rounded-control border border-line bg-surface p-1.5 shadow-hairline">
          {REASONS.map((r) => (
            <button
              key={r.value}
              className={
                "rounded-chip px-2 py-0.5 text-[11px] transition-colors " +
                (reason === r.value
                  ? "bg-red-tint text-red"
                  : "bg-inset text-ink-2 hover:bg-hover")
              }
              onClick={() => setReason(r.value)}
            >
              {r.label}
            </button>
          ))}
          <input
            className="min-w-24 rounded-[6px] border border-line bg-transparent px-1.5 py-0.5 text-[11px] text-ink outline-none placeholder:text-ink-3"
            placeholder="补充说明（可选）"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <button
            className="rounded-[6px] bg-ink px-2 py-0.5 text-[11px] text-surface transition-colors hover:bg-ink-2 disabled:opacity-40"
            disabled={!reason}
            onClick={() => void send("down")}
          >
            提交
          </button>
        </div>
      ) : null}
    </div>
  );
}
