/**
 * PointInspector（06 §8.1，单元 3.1）：按 doc_id 查 points（payload 查看）。
 * 数据源：GET /admin/qdrant/points。
 */
import { useState } from "react";

import { getPoints } from "@/api/qdrant";
import type { QdrantPointItem } from "@/types";

export function PointInspector() {
  const [docId, setDocId] = useState("");
  const [points, setPoints] = useState<QdrantPointItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  /** 触发 points 查询。 */
  async function run() {
    if (!docId.trim()) {
      setError("请输入 doc_id");
      return;
    }
    setBusy(true);
    setError(null);
    setPoints([]);
    setSearched(true);
    try {
      const resp = await getPoints(docId.trim());
      setPoints(resp.points ?? []);
    } catch {
      setError("查询失败（Qdrant 未就绪或后端未启动）");
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
          查 points
        </button>
        {busy ? <span className="text-sm text-neutral-500">查询中…</span> : null}
      </div>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {searched && points.length === 0 && !busy && !error ? (
        <p className="text-sm text-neutral-500">该 doc_id 无 points（待向量写入后查询）</p>
      ) : null}
      <ul className="space-y-2">
        {points.map((p) => (
          <li key={p.id} className="rounded border p-3">
            <div className="mb-1 flex items-center gap-2 text-xs text-neutral-500">
              <span className="font-mono">{p.chunk_id || p.id}</span>
              <span>doc_type: {String(p.payload?.doc_type ?? "-")}</span>
              <span>keywords: {String((p.payload?.keywords as string[] | undefined)?.length ?? 0)}</span>
            </div>
            <p className="text-sm">{String(p.payload?.content ?? "").slice(0, 120)}…</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
