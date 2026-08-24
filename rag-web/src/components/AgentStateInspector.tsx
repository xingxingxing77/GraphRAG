/**
 * AgentStateInspector（06 §8.1，单元 5.1）：Debug 面板 AgentState 快照查看器。
 * 消费 agentStore 快照（updates 事件写入侧随 10.3 SSE 接线）。
 */
import { useAgentStore } from "@/stores/agentStore";

/** 快照标量字段展示顺序（架构 §3.4 字段表）。 */
const FIELD_ORDER: { key: string; label: string }[] = [
  { key: "query", label: "query（改写后）" },
  { key: "original_query", label: "original_query" },
  { key: "intent", label: "intent" },
  { key: "latency_tier", label: "latency_tier" },
  { key: "current_step", label: "current_step" },
  { key: "retrieval_rounds", label: "retrieval_rounds" },
  { key: "needs_more_retrieval", label: "needs_more_retrieval" },
  { key: "faithfulness_score", label: "faithfulness_score" },
  { key: "degraded", label: "degraded" },
  { key: "token_budget_exhausted", label: "token_budget_exhausted" },
];

export function AgentStateInspector() {
  const snapshot = useAgentStore((s) => s.snapshot);

  if (!snapshot) {
    return (
      <p className="text-xs text-neutral-400">
        暂无 AgentState 快照（发起对话后由 updates 事件写入，SSE 接线随单元 10.3）。
      </p>
    );
  }

  return (
    <section className="space-y-3">
      <div className="grid gap-1.5 sm:grid-cols-2">
        {FIELD_ORDER.map(({ key, label }) => {
          const value = (snapshot as Record<string, unknown>)[key];
          if (value === undefined) return null;
          return (
            <div key={key} className="flex items-baseline gap-2 text-xs">
              <span className="w-44 shrink-0 text-neutral-400">{label}</span>
              <span className="font-mono">{String(value)}</span>
            </div>
          );
        })}
      </div>
      {snapshot.plan && snapshot.plan.length > 0 ? (
        <div>
          <p className="mb-1 text-xs font-medium text-neutral-500">plan（PlanStep 列表）</p>
          <ol className="space-y-1">
            {snapshot.plan.map((step) => (
              <li key={step.step_id} className="rounded border p-2 text-xs">
                <span className="mr-1.5 font-mono text-neutral-400">{step.step_id}</span>
                <span className="mr-1.5 rounded bg-neutral-100 px-1.5 py-0.5 dark:bg-neutral-800">
                  {step.tool}
                </span>
                <span>{step.query}</span>
                {step.status ? (
                  <span className="ml-1.5 text-neutral-400">[{step.status}]</span>
                ) : null}
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      {snapshot.received_at ? (
        <p className="text-[11px] text-neutral-400">快照时间：{snapshot.received_at}</p>
      ) : null}
    </section>
  );
}
