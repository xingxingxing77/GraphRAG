/**
 * CitationPopover（06 §8 · 批次 C BUI）：引用角标弹层。
 * surface 卡 + line 描边 + ink 文本；展示 quote 与 result_ids。
 */
import type { Citation } from "@/types";

export function CitationPopover({ citation }: { citation: Citation }) {
  return (
    <div className="w-72 rounded-card border border-line bg-surface p-3 text-left shadow-raised">
      <div className="mb-1.5 flex items-center gap-1.5">
        <span className="inline-flex h-5 w-5 items-center justify-center rounded-[4px] bg-accent-tint text-[11px] font-semibold text-accent-ink">
          {citation.marker}
        </span>
        <span className="text-xs font-medium text-ink-2">引用</span>
      </div>
      {citation.quote ? (
        <blockquote className="border-l-2 border-line px-2 py-0.5 text-xs leading-relaxed text-ink-2">
          {citation.quote}
        </blockquote>
      ) : (
        <p className="text-xs text-ink-3">（无原文摘录）</p>
      )}
      {citation.result_ids && citation.result_ids.length > 0 ? (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {citation.result_ids.map((rid) => (
            <code key={rid} className="rounded bg-inset px-1 py-0.5 text-[10px] text-ink-3">
              {rid}
            </code>
          ))}
        </div>
      ) : null}
    </div>
  );
}
