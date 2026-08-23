/**
 * IngestionPanel（06 §8.1，单元 1.1）：触发采集 + 扫描结果列表。
 * 数据源：POST /admin/ingestion/run · GET /admin/ingestion/scans。
 */
import { useCallback, useEffect, useState } from "react";

import { listScans, runIngestion } from "@/api/ingestion";
import { ScanResultTable } from "@/components/ScanResultTable";
import type { ScanRecord } from "@/types";

export function IngestionPanel() {
  const [rows, setRows] = useState<ScanRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const page = await listScans();
      setRows(page.items ?? []);
      setError(null);
    } catch {
      setError("扫描列表加载失败（后端未就绪或鉴权未接入）");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function trigger(mode: "full" | "incremental") {
    setBusy(true);
    setError(null);
    try {
      await runIngestion({ mode });
      await refresh();
    } catch {
      setError(`触发 ${mode === "full" ? "全量" : "增量"}采集失败`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        <button
          className="rounded bg-neutral-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          disabled={busy}
          onClick={() => void trigger("full")}
        >
          全量采集
        </button>
        <button
          className="rounded border px-3 py-1.5 text-sm disabled:opacity-50"
          disabled={busy}
          onClick={() => void trigger("incremental")}
        >
          增量采集
        </button>
        <button
          className="rounded border px-3 py-1.5 text-sm"
          onClick={() => void refresh()}
        >
          刷新
        </button>
        {busy ? <span className="text-sm text-neutral-500">执行中…</span> : null}
      </div>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      <ScanResultTable rows={rows} />
    </section>
  );
}
