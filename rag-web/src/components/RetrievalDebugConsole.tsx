/**
 * RetrievalDebugConsole（06 §8.1，单元 3.5）：六路开关 + 融合前后 Top-N 对比。
 * 数据源：POST /admin/debug/retrieve（六路 + fused Top-20）。
 */
import { useState } from "react";

import { debugRetrieve } from "@/api/retrieve";
import type { DebugRetrieveResponse } from "@/types";

/** 六路检索源（与 02 §2.2 SourceKind 对齐）。 */
const SOURCES = ["dense", "sparse", "graph", "global", "fulltext", "web"] as const;
type Source = (typeof SOURCES)[number];

/** 来源标签色。 */
const SOURCE_COLOR: Record<string, string> = {
  dense: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  sparse: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300",
  graph: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300",
  global: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  fulltext: "bg-cyan-100 text-cyan-700 dark:bg-cyan-950 dark:text-cyan-300",
  web: "bg-pink-100 text-pink-700 dark:bg-pink-950 dark:text-pink-300",
};

export function RetrievalDebugConsole() {
  const [query, setQuery] = useState("");
  const [enabled, setEnabled] = useState<Record<Source, boolean>>({
    dense: true,
    sparse: true,
    graph: true,
    global: true,
    fulltext: true,
    web: true,
  });
  const [result, setResult] = useState<DebugRetrieveResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** 切换单路开关。 */
  function toggle(source: Source) {
    setEnabled((prev) => ({ ...prev, [source]: !prev[source] }));
  }

  /** 触发六路检索（仅勾选路）。 */
  async function run() {
    if (!query.trim()) {
      setError("请输入查询文本");
      return;
    }
    const sources = SOURCES.filter((s) => enabled[s]);
    if (sources.length === 0) {
      setError("至少勾选一路检索源");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await debugRetrieve({ query: query.trim(), top_k: 5, sources }));
    } catch {
      setError("检索失败（后端未启动或依赖未就绪）");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
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
          六路检索
        </button>
        {busy ? <span className="text-sm text-neutral-500">检索中…</span> : null}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {SOURCES.map((s) => (
          <label key={s} className="flex items-center gap-1 text-xs">
            <input
              type="checkbox"
              checked={enabled[s]}
              onChange={() => toggle(s)}
            />
            <span>{s}</span>
          </label>
        ))}
      </div>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {result ? (
        <div className="space-y-4">
          {/* 融合后 Top-N（单元 3.5） */}
          {(result.fused ?? []).length > 0 ? (
            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="rounded-full bg-neutral-900 px-2 py-0.5 text-xs font-medium text-white dark:bg-neutral-100 dark:text-neutral-900">
                  fused
                </span>
                <span className="text-xs text-neutral-400">
                  融合后 Top-{(result.fused ?? []).length}（RRF/加权 → 送精排）
                </span>
              </div>
              <ol className="space-y-1">
                {(result.fused ?? []).slice(0, 10).map((f, i) => (
                  <li key={f.result_id} className="rounded border p-2 text-xs">
                    <span className="mr-1.5 font-mono text-neutral-400">#{i + 1}</span>
                    <span className="line-clamp-1 inline">{f.content}</span>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
          {/* 融合前分组 */}
          <div className="grid gap-4 md:grid-cols-2">
          {Object.entries(result.results ?? {}).map(([source, hits]) => (
            <div key={source}>
              <div className="mb-2 flex items-center gap-2">
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    SOURCE_COLOR[source] ?? "bg-neutral-100 dark:bg-neutral-800"
                  }`}
                >
                  {source}
                </span>
                <span className="text-xs text-neutral-400">{hits.length} 条</span>
              </div>
              <ul className="space-y-1.5">
                {hits.slice(0, 5).map((h) => (
                  <li key={h.result_id} className="rounded border p-2 text-xs">
                    <p className="line-clamp-2">{h.content}</p>
                    <p className="mt-1 text-neutral-400">
                      score: {h.score.toFixed(3)}
                      {h.chunk_id ? ` · ${h.chunk_id}` : ""}
                    </p>
                  </li>
                ))}
                {hits.length === 0 ? (
                  <li className="text-xs text-neutral-400">无召回</li>
                ) : null}
              </ul>
            </div>
          ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
