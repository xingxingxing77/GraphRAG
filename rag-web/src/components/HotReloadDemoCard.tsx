/**
 * HotReloadDemoCard（06 §8.1，单元 4.2）：rerank_threshold 热更即时生效演示。
 * 数据源：POST /admin/debug/retrieve → POST /admin/debug/rerank；
 * 阈值滑块为前端本地态即时过滤（后端 reliability.yaml 热更接口随 9.2/10.x 接线）。
 */
import { useState } from "react";

import { debugRerank } from "@/api/rerank";
import { debugRetrieve } from "@/api/retrieve";
import type { DebugRerankRankedItem } from "@/types";

export function HotReloadDemoCard() {
  const [query, setQuery] = useState("");
  const [threshold, setThreshold] = useState(0.3);
  const [ranked, setRanked] = useState<DebugRerankRankedItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  /** 拉取精排候选（Top-8）。 */
  async function load() {
    if (!query.trim()) {
      setError("请输入查询文本");
      return;
    }
    setBusy(true);
    setError(null);
    setRanked([]);
    setLoaded(true);
    try {
      const retr = await debugRetrieve({ query: query.trim(), top_k: 8 });
      const candidates = (retr.fused ?? []).slice(0, 8);
      if (candidates.length === 0) {
        setError("无候选文档（请先完成知识库索引）");
        return;
      }
      const rr = await debugRerank({
        query: query.trim(),
        docs: candidates.map((c) => ({ content: c.content })),
        top_k: 8,
      });
      setRanked(rr.ranked ?? []);
    } catch {
      setError("加载失败（后端未启动或依赖未就绪）");
    } finally {
      setBusy(false);
    }
  }

  // 阈值即时过滤（热更演示：拖动滑块立即生效）
  const evidence = ranked.filter((r) => r.score >= threshold);

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
          onClick={() => void load()}
        >
          加载证据
        </button>
        {busy ? <span className="text-sm text-neutral-500">加载中…</span> : null}
      </div>
      <div className="flex items-center gap-3">
        <label className="text-sm text-neutral-500">rerank_threshold</label>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
          className="w-48"
        />
        <span className="font-mono text-sm">{threshold.toFixed(2)}</span>
        <span className="text-xs text-neutral-400">
          送入 Agent 证据数：{evidence.length}（≤ Top-K 且含分数）
        </span>
      </div>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {loaded && ranked.length === 0 && !busy && !error ? (
        <p className="text-sm text-neutral-500">无精排结果</p>
      ) : null}
      {ranked.length > 0 ? (
        <ul className="space-y-1">
          {ranked.map((r, i) => {
            const kept = r.score >= threshold;
            return (
              <li
                key={`${r.content.slice(0, 16)}-${i}`}
                className={`rounded border p-2 text-xs ${
                  kept ? "" : "opacity-35 line-through"
                }`}
              >
                <span className="mr-1.5 font-mono text-neutral-400">#{i + 1}</span>
                <span className="line-clamp-1 inline">{r.content}</span>
                <span className="ml-1 text-neutral-400">({r.score.toFixed(3)})</span>
              </li>
            );
          })}
        </ul>
      ) : null}
      <p className="text-[11px] text-neutral-400">
        说明：滑块为前端本地态即时演示；reliability.yaml 服务端热更接口随单元 9.2/10.x 接线。
      </p>
    </section>
  );
}
