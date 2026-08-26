/**
 * MarkdownAnswer（06 §8.2 批次 B）：answer 的 Markdown 渲染 + 内联 [n] 引用角标。
 * react-markdown + rehype-highlight（用户定案引入，2026-08-24）；
 * 「[n] 解析」将正文中的 [数字] 标记替换为可点击角标 → CitationPopover。
 */
import { useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";

import { CitationPopover } from "@/components/CitationPopover";
import type { Citation } from "@/types";

function CitationMarker({ citation }: { citation: Citation }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block align-top">
      <button
        className="mx-0.5 -translate-y-0.5 rounded-[4px] bg-accent-tint px-0.5 text-[11px] font-semibold text-accent-ink hover:bg-hover"
        onClick={() => setOpen((v) => !v)}
        aria-label={"引用 " + citation.marker}
      >
        [{citation.marker}]
      </button>
      {open ? (
        <span className="absolute bottom-full left-1/2 z-20 -translate-x-1/2 pb-1" onMouseLeave={() => setOpen(false)}>
          <CitationPopover citation={citation} />
        </span>
      ) : null}
    </span>
  );
}

const MARKER_RE = /(\[\d+\])/g;
const MARKER_ONLY_RE = /^\[(\d+)\]$/;

function renderInline(content: string, citations: Citation[]): ReactNode[] {
  const parts = content.split(MARKER_RE);
  return parts.map((part, i) => {
    const m = part.match(MARKER_ONLY_RE);
    if (m) {
      const marker = Number(m[1]);
      const citation = citations.find((c) => c.marker === marker);
      if (!citation) return <span key={i}>[{marker}]</span>;
      return <CitationMarker key={i} citation={citation} />;
    }
    if (!part) return null;
    return (
      <ReactMarkdown key={i} rehypePlugins={[rehypeHighlight]}>
        {part}
      </ReactMarkdown>
    );
  });
}

export function MarkdownAnswer({ content, citations }: { content: string; citations?: Citation[] }) {
  return <div className="max-w-full">{renderInline(content, citations ?? [])}</div>;
}
