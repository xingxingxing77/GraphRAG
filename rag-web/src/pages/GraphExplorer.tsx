/**
 * GraphExplorerPage（06 §7 v1.3）：全屏画布 + 节点检视器。
 * 顶部实体搜索（depth≤3/limit≤200，02 §3.6 约束）；InteractiveNvlWrapper
 * 力导图渲染；节点点击 → 右侧检视器（fine-tune-card 落点：label/type/zone
 * + 邻居列表），点邻居 = 以该实体重查"走图"；zone core/open 着色图例；
 * 404 换词 / 503 no-graph 走 DegradedBanner（06 §9）。
 */
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { InteractiveNvlWrapper } from "@neo4j-nvl/react";
import type { Node as NvlNode } from "@neo4j-nvl/base";
import { ArrowLeft } from "lucide-react";

import { DegradedBanner } from "@/components/DegradedBanner";
import { getSubgraph } from "@/api/graph";
import { useChatStore } from "@/stores/chatStore";
import type { SubgraphResponse } from "@/types";

/** NVL 关系元素（id/from/to/caption）。 */
interface NvlRel {
  id: string;
  from: string;
  to: string;
  caption: string;
}

/** zone → 节点颜色（core 实色 / open 灰，图例同源）。 */
const ZONE_COLOR: Record<string, string> = {
  core: "#5b5bf0",
  open: "#8b919c",
  pending: "#a0a0a0",
};

/**
 * 将后端子图响应映射为 NVL 元素（zone 决定节点色）。
 *
 * @param subgraph - SubgraphResponse。
 * @returns { nodes, rels } NVL 元素。
 */
function toNvl(subgraph: SubgraphResponse): { nodes: NvlNode[]; rels: NvlRel[] } {
  const nodes: NvlNode[] = (subgraph.nodes ?? []).map((n) => ({
    id: n.id,
    caption: n.label,
    color: ZONE_COLOR[n.zone] ?? ZONE_COLOR.open,
    size: n.zone === "core" ? 14 : 10,
  }));
  const rels: NvlRel[] = (subgraph.relationships ?? []).map((r, i) => ({
    id: `rel-${i}-${r.source}-${r.target}`,
    from: r.source,
    to: r.target,
    caption: r.type,
  }));
  return { nodes, rels };
}

/** 画布中央提示（空态/错误共用）。 */
function CanvasHint({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
      <p className="text-sm font-medium text-neutral-500">{title}</p>
      {sub ? <p className="mt-1 text-xs text-neutral-400">{sub}</p> : null}
    </div>
  );
}

export default function GraphExplorerPage() {
  const [entity, setEntity] = useState("");
  const [depth, setDepth] = useState(2);
  const [limit, setLimit] = useState(50);
  const [result, setResult] = useState<SubgraphResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [errCode, setErrCode] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const pushDegraded = useChatStore((s) => s.pushDegraded);

  const nvl = useMemo(() => (result ? toNvl(result) : null), [result]);
  const selected = useMemo(
    () => (result?.nodes ?? []).find((n) => n.id === selectedId) ?? null,
    [result, selectedId],
  );

  /** 邻居列表（检视器"走图"入口，按当前子图关系推导）。 */
  const neighbors = useMemo(() => {
    if (!result || !selectedId) return [];
    const ids = new Set<string>();
    for (const r of result.relationships ?? []) {
      if (r.source === selectedId) ids.add(r.target);
      if (r.target === selectedId) ids.add(r.source);
    }
    return (result.nodes ?? []).filter((n) => ids.has(n.id));
  }, [result, selectedId]);

  /** 子图查询（钳制 depth≤3/limit≤200，02 §3.6）。 */
  const search = useCallback(
    async (name: string) => {
      const q = name.trim();
      if (!q) return;
      setBusy(true);
      setErrCode(null);
      setSelectedId(null);
      try {
        setResult(await getSubgraph(q, Math.min(depth, 3), Math.min(limit, 200)));
      } catch (e) {
        const code =
          (e as { response?: { data?: { code?: string } } })?.response?.data?.code ?? null;
        setErrCode(code ?? "UNKNOWN");
        if (code === "GRAPH_503_STORE_UNAVAILABLE") pushDegraded(["no-graph"]);
      } finally {
        setBusy(false);
      }
    },
    [depth, limit, pushDegraded],
  );

  return (
    <div className="flex h-screen flex-col">
      {/* 顶栏：返回 + 标题 + 搜索 + 深度/条数 */}
      <header className="flex items-center gap-3 border-b px-4 py-2.5">
        <Link
          to="/chat"
          className="flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
        >
          <ArrowLeft size={15} /> 聊天
        </Link>
        <h1 className="text-sm font-semibold">图谱浏览器</h1>
        <span className="flex-1" />
        <input
          className="w-64 rounded-xl border border-neutral-200 bg-white px-3 py-1.5 text-sm outline-none focus:border-neutral-400 dark:border-neutral-700 dark:bg-neutral-800"
          placeholder="规范实体名（如：番茄 / 清蒸鲈鱼）"
          value={entity}
          onChange={(e) => setEntity(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void search(entity);
          }}
        />
        <select
          className="rounded-lg border border-neutral-200 bg-white px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
          value={depth}
          onChange={(e) => setDepth(Number(e.target.value))}
          aria-label="扩展深度"
        >
          {[1, 2, 3].map((d) => (
            <option key={d} value={d}>
              深度 {d}
            </option>
          ))}
        </select>
        <select
          className="rounded-lg border border-neutral-200 bg-white px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-800"
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
          aria-label="节点上限"
        >
          {[50, 100, 200].map((l) => (
            <option key={l} value={l}>
              上限 {l}
            </option>
          ))}
        </select>
        <button
          className="rounded-xl bg-neutral-900 px-3.5 py-1.5 text-sm text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900"
          disabled={busy || !entity.trim()}
          onClick={() => void search(entity)}
        >
          {busy ? "查询中…" : "查询"}
        </button>
      </header>

      <DegradedBanner />

      <div className="flex min-h-0 flex-1">
        {/* 画布区 */}
        <div className="relative min-w-0 flex-1">
          {nvl && nvl.nodes.length > 0 ? (
            <InteractiveNvlWrapper
              key={nvl.nodes.map((n) => n.id).join(",")}
              nodes={nvl.nodes}
              rels={nvl.rels}
              layout="forceDirected"
              mouseEventCallbacks={{
                onNodeClick: (node) => setSelectedId(node.id),
                onCanvasClick: () => setSelectedId(null),
              }}
            />
          ) : (
            <div className="absolute inset-0">
              {busy ? (
                <CanvasHint title="查询中…" />
              ) : errCode === "GRAPH_404_ENTITY_NOT_FOUND" ? (
                <CanvasHint title="未收录该实体" sub="试试其他关键词" />
              ) : errCode === "GRAPH_503_STORE_UNAVAILABLE" ? (
                <CanvasHint title="图谱服务暂不可用" sub="已降级（no-graph），恢复后自动可用" />
              ) : errCode ? (
                <CanvasHint title="子图查询失败" sub="后端未就绪或参数有误" />
              ) : (
                <CanvasHint title="搜索一个实体开始探索" sub="例如：清蒸鲈鱼" />
              )}
            </div>
          )}
          {/* 图例（zone 语义，J12） */}
          {nvl && nvl.nodes.length > 0 ? (
            <div className="absolute bottom-3 left-3 rounded-xl border border-neutral-200 bg-white/90 px-3 py-2 text-[11px] text-neutral-600 shadow-sm dark:border-neutral-700 dark:bg-neutral-800/90 dark:text-neutral-300">
              <p className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: ZONE_COLOR.core }} />
                core（白名单）
              </p>
              <p className="mt-1 flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: ZONE_COLOR.open }} />
                open（开放区）
              </p>
            </div>
          ) : null}
        </div>

        {/* 检视器（fine-tune-card 落点） */}
        <aside className="w-80 shrink-0 overflow-y-auto border-l p-4">
          {!selected ? (
            <p className="text-xs text-neutral-400">点击画布节点查看详情与邻居</p>
          ) : (
            <div>
              <p className="text-base font-semibold">{selected.label}</p>
              <div className="mt-2 flex items-center gap-2 text-xs">
                <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300">
                  {selected.type}
                </span>
                <span
                  className="rounded-full px-2 py-0.5 text-white"
                  style={{ background: ZONE_COLOR[selected.zone] ?? ZONE_COLOR.open }}
                >
                  {selected.zone}
                </span>
              </div>
              <p className="mt-4 text-xs font-medium text-neutral-500">
                邻居（{neighbors.length}）
              </p>
              <ul className="mt-1.5 space-y-1">
                {neighbors.map((n) => (
                  <li key={n.id}>
                    <button
                      className="w-full truncate rounded-lg px-2 py-1.5 text-left text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800"
                      onClick={() => {
                        setEntity(n.label);
                        void search(n.label);
                      }}
                      title={`以 ${n.label} 为中心重新查询`}
                    >
                      {n.label}
                      <span className="ml-1.5 text-[11px] text-neutral-400">{n.type}</span>
                    </button>
                  </li>
                ))}
                {neighbors.length === 0 ? (
                  <li className="px-2 text-xs text-neutral-400">无邻居节点</li>
                ) : null}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
