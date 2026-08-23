/**
 * ChunkBoundaryViewer（06 §8.1，单元 2.1）：分块可视化调试页。
 * chunk 边界高亮、title_path 显示；数据源：POST /admin/chunking/preview。
 */
import { useState } from "react";

import { previewChunking } from "@/api/chunking";
import type { Chunk } from "@/types";

/**
 * 单个 chunk 卡片：展示 title_path、字符区间、内容与 metadata 字段区。
 */
function ChunkCard({ chunk }: { chunk: Chunk }) {
  const metadata = chunk.metadata ?? {};
  const metaEntries = Object.entries(metadata).filter(
    ([, v]) => typeof v !== "object" || v === null,
  );
  return (
    <div className="rounded border border-neutral-300 dark:border-neutral-700">
      <div className="flex items-center justify-between border-b px-3 py-1.5 text-xs text-neutral-500">
        <span className="font-mono">{chunk.chunk_id}</span>
        <span>
          [{chunk.position.start_char}, {chunk.position.end_char}) ·{" "}
          {chunk.content.length} 字符
        </span>
      </div>
      {chunk.title_path && chunk.title_path.length > 0 ? (
        <p className="px-3 pt-1.5 text-xs text-neutral-400">
          {chunk.title_path.join(" > ")}
        </p>
      ) : null}
      <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap px-3 py-2 text-xs">
        {chunk.content}
      </pre>
      {/* metadata 字段区（单元 2.2：Chunk 详情面板扩展） */}
      {metaEntries.length > 0 ? (
        <div className="border-t px-3 py-1.5 text-xs text-neutral-500">
          {metaEntries.map(([k, v]) => (
            <span key={k} className="mr-3">
              <span className="text-neutral-400">{k}:</span> {String(v)}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/**
 * 分块边界预览面板：输入 doc_id，触发解析→清洗→分块并渲染块列表。
 */
export function ChunkBoundaryViewer() {
  const [docId, setDocId] = useState("");
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** 触发分块预览。 */
  async function run() {
    if (!docId.trim()) {
      setError("请输入 doc_id（先执行采集）");
      return;
    }
    setBusy(true);
    setError(null);
    setChunks([]);
    try {
      const resp = await previewChunking({ doc_id: docId.trim() });
      setChunks(resp.chunks ?? []);
    } catch {
      setError("分块预览失败（doc_id 不在最近批次或后端未就绪）");
    } finally {
      setBusy(false);
    }
  }

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
          分块预览
        </button>
        {busy ? <span className="text-sm text-neutral-500">执行中…</span> : null}
      </div>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {chunks.length > 0 ? (
        <div className="space-y-2">
          <p className="text-sm text-neutral-500">共 {chunks.length} 个块</p>
          {chunks.map((c) => (
            <ChunkCard key={c.chunk_id} chunk={c} />
          ))}
        </div>
      ) : null}
    </section>
  );
}
