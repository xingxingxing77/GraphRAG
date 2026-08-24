/**
 * RerankCompareView（06 §8.1，单元 4.1）：rerank 前后排序对比视图。
 * 数据源：POST /admin/debug/retrieve（取 fused Top-N）→ POST /admin/debug/rerank。
 */
import { useState } from "react";

import { debugRerank } from "@/api/rerank";
import { debugRetrieve } from "@/api/retrieve";
import type { DebugRerankRankedItem } from "@/types";

export function RerankCompareView() {
  const [query, setQuery] = useState("");
  const [before, setBefore] = useState<{ content: string; score: number }[]>([]);
  const [after, setAfter] = useState<DebugRerankRankedItem[]>([]);
  const [degraded, setDegraded] = useState(false);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** 取融合 Top-N 作候选 → 调精排对比。 */
  async function run() {
    if (!query.trim()) {
      setError("请输入查询文本");
      return;
    }
    setBusy(true);
    setError(null);
    setBefore([]);
    setAfter([]);
    setDegraded(false);
    setElapsedMs(null);
    try {
      const retr = await debugRetrieve({ query: query.trim(), top_k: 8 });
      const candidates = (retr.fused ?? []).slice(0, 8);
      if (candidates.length === 0) {
        setError("无候选文档（请先完成知识库索引）");
        return;
      }
      setBefore(candidates.map((c) => ({ content: c.content, score: 0 })));
      const rr = await debugRerank({
        query: query.trim(),
        docs: candidates.map((c) => ({ content: c.content })),
        top_k: 5,
      });
      setAfter(rr.ranked ?? []);
      setDegraded(rr.degraded);
      setElapsedMs(rr.elapsed_ms);
    } catch {
      setError("精排对比失败（后端未启动或依赖未就绪）");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        <input
          className="w-64 rounded border px-3 py-1.5 text-sm"
          placeholder="查询文本"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          className="rounded border px-3 py-1.5 text-sm disabled:opacity-50"
          disabled={busy}
          onClick={() => void run()}
        >
          精排对比
        </button>
        {busy ? <span className="text-sm text-neutral-500">精排中…</span> : null}
        {elapsedMs !== null ? (
          <span className="text-xs text-neutral-400">{elapsedMs}ms</span>
        ) : null}
      </div>
      {degraded ? (
        <p className="rounded border border-orange-200 bg-orange-50 px-3 py-1.5 text-xs text-orange-700 dark:border-orange-900 dark:bg-orange-950/40 dark:text-orange-300">
          no-rerank 降级：FlagEmbedding 未就绪/超时，已返回粗排原序（X-Degraded: no-rerank）
        </p>
      ) : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {before.length > 0 || after.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-medium text-neutral-500">
              粗排（融合 Top-N 原序）
            </p>
            <ol className="space-y-1">
              {before.map((c, i) => (
                <li key={`b-${i}`} className="rounded border p-2 text-xs">
                  <span className="mr-1.5 font-mono text-neutral-400">#{i + 1}</span>
                  <span className="line-clamp-1 inline">{c.content}</span>
                </li>
              ))}
            </ol>
          </div>
          <div>
            <p className="mb-2 text-xs font-medium text-neutral-500">精排后（Top-K）</p>
            <ol className="space-y-1">
              {after.map((c, i) => (
                <li key={`a-${i}`} className="rounded border p-2 text-xs">
                  <span className="mr-1.5 font-mono text-neutral-400">#{i + 1}</span>
                  <span className="line-clamp-1 inline">{c.content}</span>
                  <span className="ml-1 text-neutral-400">({c.score.toFixed(3)})</span>
                </li>
              ))}
              {after.length === 0 ? (
                <li className="text-xs text-neutral-400">无精排结果</li>
              ) : null}
            </ol>
          </div>
        </div>
      ) : null}
    </section>
  );
}
