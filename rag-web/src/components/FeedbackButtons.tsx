/**
 * FeedbackButtons（06 §8）：up/down → POST /feedback（02 §3.5）。
 * down 必选 reason（wrong/incomplete/unsafe/other）+ 可选 comment；点踩进 bad case 队列（D8 回流）。
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
  "flex h-7 w-7 items-center justify-center rounded-full border transition-colors ";

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
      ? "border-green-300 bg-green-50 text-green-600 dark:bg-green-950 dark:text-green-300"
      : "border-neutral-200 hover:border-neutral-300 dark:border-neutral-700");
  const downCls =
    BASE_BTN +
    (rating === "down"
      ? "border-orange-300 bg-orange-50 text-orange-600 dark:bg-orange-950 dark:text-orange-300"
      : "border-neutral-200 hover:border-neutral-300 dark:border-neutral-700");

  return (
    <div className="mt-1.5 flex items-center gap-1.5 text-neutral-400">
      <button className={upCls} onClick={() => void send("up")} aria-label="点赞" title="有用">
        <ThumbsUp size={13} />
      </button>
      <button className={downCls} onClick={() => void send("down")} aria-label="点踩" title="点踩（需选原因）">
        <ThumbsDown size={13} />
      </button>
      {picking ? (
        <div className="ml-1 flex flex-wrap items-center gap-1.5 rounded-lg border border-neutral-200 bg-white p-1.5 dark:border-neutral-700 dark:bg-neutral-800">
          {REASONS.map((r) => (
            <button
              key={r.value}
              className={
                "rounded-full px-2 py-0.5 text-[11px] transition-colors " +
                (reason === r.value
                  ? "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300"
                  : "bg-neutral-100 text-neutral-500 hover:bg-neutral-200 dark:bg-neutral-900 dark:text-neutral-400")
              }
              onClick={() => setReason(r.value)}
            >
              {r.label}
            </button>
          ))}
          <input
            className="min-w-24 rounded border border-neutral-200 bg-transparent px-1.5 py-0.5 text-[11px] outline-none dark:border-neutral-600"
            placeholder="补充说明（可选）"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <button
            className="rounded bg-orange-500 px-2 py-0.5 text-[11px] text-white hover:bg-orange-600 disabled:opacity-40"
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
