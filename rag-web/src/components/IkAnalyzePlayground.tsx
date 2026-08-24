/**
 * IkAnalyzePlayground（06 §8.1，单元 3.2）：IK 分词效果调试页。
 * 数据源：POST /admin/debug/analyze（_analyze 封装）。
 */
import { useState } from "react";

import { analyzeText } from "@/api/analyze";

/** 可选索引（02 §3.11：rag_entities | rag_chunks）。 */
const INDEX_OPTIONS = ["rag_entities", "rag_chunks"] as const;

export function IkAnalyzePlayground() {
  const [index, setIndex] = useState<(typeof INDEX_OPTIONS)[number]>("rag_entities");
  const [text, setText] = useState("");
  const [tokens, setTokens] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analyzed, setAnalyzed] = useState(false);

  /** 触发分词。 */
  async function run() {
    if (!text.trim()) {
      setError("请输入待分词文本");
      return;
    }
    setBusy(true);
    setError(null);
    setTokens([]);
    setAnalyzed(true);
    try {
      const resp = await analyzeText({ index, text: text.trim() });
      setTokens(resp.tokens ?? []);
    } catch {
      setError("分词失败（ES/IK 未就绪或后端未启动）");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <select
          className="rounded border px-2 py-1.5 text-sm"
          value={index}
          onChange={(e) => setIndex(e.target.value as (typeof INDEX_OPTIONS)[number])}
        >
          {INDEX_OPTIONS.map((i) => (
            <option key={i} value={i}>
              {i}
            </option>
          ))}
        </select>
        <input
          className="w-72 rounded border px-3 py-1.5 text-sm"
          placeholder="待分词文本（如：清蒸鲈鱼的做法）"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button
          className="rounded border px-3 py-1.5 text-sm disabled:opacity-50"
          disabled={busy}
          onClick={() => void run()}
        >
          分词
        </button>
        {busy ? <span className="text-sm text-neutral-500">分词中…</span> : null}
      </div>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {analyzed && tokens.length === 0 && !busy && !error ? (
        <p className="text-sm text-neutral-500">无分词结果</p>
      ) : null}
      {tokens.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {tokens.map((t, i) => (
            <span
              key={`${t}-${i}`}
              className="rounded-full border border-neutral-300 bg-white px-2.5 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-800"
            >
              {t}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
