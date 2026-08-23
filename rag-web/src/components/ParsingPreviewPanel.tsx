/**
 * ParsingPreviewPanel（06 §8.1，单元 1.2）：上传样例文件调试页。
 * 限支持格式（md/html/pdf），展示解析文本与标题树。
 * 数据源：POST /admin/parsing/preview。
 */
import { useRef, useState } from "react";

import { previewFile } from "@/api/parsing";
import type { ParsingPreviewResponse } from "@/types";

const ACCEPT = ".md,.markdown,.html,.htm,.pdf";

export function ParsingPreviewPanel() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<ParsingPreviewResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await previewFile(file));
    } catch {
      setError("解析失败（格式不支持或后端未就绪）");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => void onPick(e)}
        />
        <button
          className="rounded border px-3 py-1.5 text-sm disabled:opacity-50"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          选择样例文件（md / html / pdf）
        </button>
        {busy ? <span className="text-sm text-neutral-500">解析中…</span> : null}
      </div>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {result ? (
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <h3 className="mb-2 text-sm font-medium">标题树（structure_tree）</h3>
            <ul className="space-y-1 text-sm">
              {(result.structure_tree ?? []).map((n, i) => (
                <li key={i} style={{ paddingLeft: (n.level - 1) * 16 }}>
                  <span className="text-neutral-500">H{n.level}</span> {n.title}
                  <span className="ml-1 text-xs text-neutral-400">@{n.start_offset}</span>
                </li>
              ))}
              {(result.structure_tree ?? []).length === 0 ? (
                <li className="text-neutral-500">（无标题结构）</li>
              ) : null}
            </ul>
            <p className="mt-2 text-xs text-neutral-500">
              format_meta: {JSON.stringify(result.format_meta)}
            </p>
          </div>
          <div>
            <h3 className="mb-2 text-sm font-medium">解析文本（前 500 字）</h3>
            <pre className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded border p-3 text-xs">
              {result.text.slice(0, 500)}
            </pre>
          </div>
        </div>
      ) : null}
    </section>
  );
}
