/**
 * ThoughtPanel（06 §8 · 批次 C BUI 业务包装）：思考过程折叠面板。
 * BUI thinking-state（Steps 变体）视觉：星标头 + 展开追踪 + 校验勾，
 * 流式期间自动展开、末行 spinner；点击头可手动折叠。
 */
import { useState } from "react";

import type { ThoughtStep } from "@/stores/chatStore";

function Sparkle() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="var(--ink-2)">
      <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8z" />
    </svg>
  );
}

function Check() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="var(--ink-3)"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0"
    >
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}

export function ThoughtPanel({ steps, streaming }: { steps: ThoughtStep[]; streaming: boolean }) {
  const [manual, setManual] = useState<boolean | null>(null);
  // streaming 结束自动收起（用户未手动操作时），避免完成后常驻展开（P2-02）
  const expanded = manual ?? streaming;

  return (
    <div className="mx-auto w-full max-w-3xl">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setManual((v) => !(v ?? streaming))}
        className="flex w-fit items-center gap-2 rounded-control px-1.5 py-1 text-left transition-colors duration-100 hover:bg-hover-2"
      >
        <Sparkle />
        <span className="text-[13px] font-medium text-ink-2">
          {streaming ? "思考中…" : "思考过程（" + steps.length + "）"}
        </span>
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--ink-3)"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="transition-transform duration-300"
          style={{ transform: expanded ? "rotate(180deg)" : "rotate(0)" }}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      <div
        className="grid transition-[grid-template-rows,opacity] duration-400"
        style={{
          gridTemplateRows: expanded ? "1fr" : "0fr",
          opacity: expanded ? 1 : 0,
          transitionTimingFunction: "cubic-bezier(0.23, 1, 0.32, 1)",
        }}
      >
        <div className="overflow-hidden">
          <ol className="mt-1 ml-[5px] space-y-1 border-l border-line pl-4">
            {steps.map((t, i) => (
              <li
                key={t.node + "_" + i + "_" + t.summary.slice(0, 8)}
                className="flex min-h-7 items-center gap-2 rounded-[6px] px-1.5 py-0.5"
              >
                {i < steps.length - 1 || !streaming ? (
                  <Check />
                ) : (
                  <span
                    className="size-3 shrink-0 rounded-full border-[1.5px] border-line-strong border-t-ink-2"
                    style={{ animation: "spin 700ms linear infinite" }}
                  />
                )}
                <span className="rounded bg-inset px-1.5 py-0.5 font-mono text-[10px] text-ink-2">
                  {t.node}
                </span>
                <span className="min-w-0 truncate text-[12.5px] font-medium text-ink">{t.summary}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}
