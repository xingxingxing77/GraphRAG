/**
 * EmbeddingProbeCard（06 §8.1，单元 2.3）：检索调试台雏形。
 * 输入文本显示 dense 维数 / sparse 键数 / 耗时。
 * 数据源：POST /admin/debug/embed。
 */
import { useState } from "react";

import { probeEmbed } from "@/api/debug";
import type { EmbedProbeResponse } from "@/types";

export function EmbeddingProbeCard() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<EmbedProbeResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** 触发向量探针。 */
  async function run() {
    if (!text.trim()) {
      setError("请输入探针文本");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await probeEmbed({ text: text.trim() }));
    } catch {
      setError("探针失败（Ollama/bge-m3 未就绪或后端未启动）");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        <input
          className="w-72 rounded border px-3 py-1.5 text-sm"
          placeholder="探针文本"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button
          className="rounded border px-3 py-1.5 text-sm disabled:opacity-50"
          disabled={busy}
          onClick={() => void run()}
        >
          向量探针
        </button>
        {busy ? <span className="text-sm text-neutral-500">执行中…</span> : null}
      </div>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {result ? (
        <div className="flex gap-6 text-sm">
          <span>
            dense 维数：<span className="font-mono">{result.dense_dims}</span>
          </span>
          <span>
            sparse 键数：<span className="font-mono">{result.sparse_keys}</span>
          </span>
          <span>
            耗时：<span className="font-mono">{result.latency_ms} ms</span>
          </span>
        </div>
      ) : null}
    </section>
  );
}
