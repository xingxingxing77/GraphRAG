/**
 * ScanResultTable（06 §8.1，单元 1.1）。
 * 数据源：GET /admin/ingestion/scans；BUI 落点：records-table（10.7 替换）。
 */
import type { ScanRecord } from "@/types";

export function ScanResultTable({ rows }: { rows: ScanRecord[] }) {
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b text-left text-neutral-500">
          <th className="py-2 pr-4">扫描 ID</th>
          <th className="py-2 pr-4">模式</th>
          <th className="py-2 pr-4">发现</th>
          <th className="py-2 pr-4">变更</th>
          <th className="py-2 pr-4">去重拦截</th>
          <th className="py-2">完成时间</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.scan_id} className="border-b">
            <td className="py-2 pr-4 font-mono text-xs">{r.scan_id}</td>
            <td className="py-2 pr-4">{r.mode === "full" ? "全量" : "增量"}</td>
            <td className="py-2 pr-4">{r.discovered}</td>
            <td className="py-2 pr-4">{r.changed}</td>
            <td className="py-2 pr-4">{r.deduped}</td>
            <td className="py-2 text-neutral-500">
              {r.finished_at ? new Date(r.finished_at).toLocaleString() : "—"}
            </td>
          </tr>
        ))}
        {rows.length === 0 ? (
          <tr>
            <td colSpan={6} className="py-4 text-center text-neutral-500">
              暂无扫描记录
            </td>
          </tr>
        ) : null}
      </tbody>
    </table>
  );
}
