/**
 * CleaningDiffCard（06 §8.1，单元 1.3）：清洗前后对比预览。
 * diff 高亮被删片段；数据源：POST /admin/cleaning/preview。
 * BUI 落点：diff-table（10.7 替换）。
 */
import { useState } from "react";

import { previewCleaning } from "@/api/cleaning";
import type { CleaningPreviewResponse } from "@/types";

export function CleaningDiffCard() {
  const [docId, setDocId] = useState("");
  const [result, setResult] = useState<CleaningPreviewResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (!docId.trim()) {
      setError("请输入 doc_id（先执行采集）");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await previewCleaning({ doc_id: docId.trim() }));
    } catch {
      setError("清洗预览失败（doc_id 不在最近批次或后端未就绪）");
    } finally {
      setBusy(false);
    }
  }

  const removed = new Set(result?.removed_spans ?? []);

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        <input
          className="w-72 rounded border px-3 py-1.5 text-sm"
          placeholder="doc_id（最近采集批次）"
          value={docId}
          onChange={(e) => setDocId(e.target.value)}
        />
        <button
          className="rounded border px-3 py-1.5 text-sm disabled:opacity-50"
          disabled={busy}
          onClick={() => void run()}
        >
          清洗预览
        </button>
        {busy ? <span className="text-sm text-neutral-500">执行中…</span> : null}
      </div>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {result ? (
        <div className="space-y-3">
          <p className="text-sm">
            quality_score：
            <span className="font-mono">{result.quality_score.toFixed(2)}</span>
            <span className="ml-2 text-neutral-500">
              被删片段 {(result.removed_spans ?? []).length} 处
            </span>
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-medium">清洗前</h3>
              <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded border p-3 text-xs">
                {result.before
                  .split("\n")
                  .map((ln, i) => (
                    <span
                      key={i}
                      className={
                        removed.has(ln.trim()) && ln.trim()
                          ? "block bg-red-100 dark:bg-red-950"
                          : "block"
                      }
                    >
                      {ln}
                    </span>
                  ))}
              </pre>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-medium">清洗后</h3>
              <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded border p-3 text-xs">
                {result.after}
              </pre>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
