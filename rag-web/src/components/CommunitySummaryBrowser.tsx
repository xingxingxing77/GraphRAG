/**
 * CommunitySummaryBrowser（06 §8.1，单元 2.6）：Admin 社区摘要浏览只读卡片。
 * level 过滤；数据源：GET /admin/communities。
 */
import { useCallback, useEffect, useState } from "react";

import { listCommunities } from "@/api/communities";
import type { CommunitySummaryItem } from "@/types";

export function CommunitySummaryBrowser() {
  const [level, setLevel] = useState<number | undefined>(undefined);
  const [items, setItems] = useState<CommunitySummaryItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** 加载社区摘要列表。 */
  const load = useCallback(async (lv?: number) => {
    setBusy(true);
    setError(null);
    try {
      const page = await listCommunities(lv);
      setItems(page.items ?? []);
    } catch {
      setError("加载失败（Neo4j 未就绪或尚无社区数据）");
      setItems([]);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load(level);
  }, [level, load]);

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-sm text-neutral-500">层级过滤：</span>
        {([undefined, 0, 1] as const).map((lv) => (
          <button
            key={String(lv)}
            className={`rounded border px-3 py-1 text-sm ${
              level === lv ? "bg-neutral-900 text-white" : ""
            }`}
            onClick={() => setLevel(lv)}
          >
            {lv === undefined ? "全部" : lv === 0 ? "叶子（L0）" : "父层（L1）"}
          </button>
        ))}
        {busy ? <span className="text-sm text-neutral-500">加载中…</span> : null}
      </div>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      <ul className="space-y-2">
        {items.map((c) => (
          <li key={c.community_id} className="rounded border p-3">
            <div className="mb-1 flex items-center gap-2 text-xs text-neutral-500">
              <span className="font-mono">{c.community_id}</span>
              <span>L{c.level}</span>
              <span>{c.size} 成员</span>
            </div>
            <p className="text-sm">{c.summary || "（暂无摘要）"}</p>
          </li>
        ))}
        {items.length === 0 && !busy && !error ? (
          <li className="text-sm text-neutral-500">暂无社区数据（待图谱构建后生成）</li>
        ) : null}
      </ul>
    </section>
  );
}
