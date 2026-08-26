/**
 * CitationPopover（06 §8）：引用角标弹层。
 * 展示 quote 与 result_ids，锚定 [n] 标记（单元 10.8 批次 B）。
 */
import type { Citation } from "@/types";

export function CitationPopover({ citation }: { citation: Citation }) {
  return (
    <div className="w-72 rounded-xl border border-neutral-200 bg-white p-3 text-left shadow-lg dark:border-neutral-700 dark:bg-neutral-800">
      <div className="mb-1.5 flex items-center gap-1.5">
        <span className="inline-flex h-5 w-5 items-center justify-center rounded bg-blue-100 text-[11px] font-semibold text-blue-700 dark:bg-blue-950 dark:text-blue-300">
          {citation.marker}
        </span>
        <span className="text-xs font-medium text-neutral-700 dark:text-neutral-200">引用</span>
      </div>
      {citation.quote ? (
        <blockquote className="border-l-2 border-neutral-200 px-2 py-0.5 text-xs leading-relaxed text-neutral-500 dark:border-neutral-600 dark:text-neutral-400">
          {citation.quote}
        </blockquote>
      ) : (
        <p className="text-xs text-neutral-400">（无原文摘录）</p>
      )}
      {citation.result_ids && citation.result_ids.length > 0 ? (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {citation.result_ids.map((rid) => (
            <code key={rid} className="rounded bg-neutral-100 px-1 py-0.5 text-[10px] text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
              {rid}
            </code>
          ))}
        </div>
      ) : null}
    </div>
  );
}
