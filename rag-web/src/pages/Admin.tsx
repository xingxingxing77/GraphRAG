/**
 * AdminPage（06 §7 v1.3）：左侧分区导航 + 卡片流（role=admin 门禁）。
 * 五分区（§8.1 分区归属）：总览（HealthOverview+ProfileBadge）/ 管道 /
 * 检索 / Agent（AgentFlowOverview）/ 系统。admin.debug_enabled=false 时
 * 管道/检索/Agent 调试分区隐藏（SYS_403_DEBUG_DISABLED 语义）——该开关
 * 尚未随 /config/public 暴露（02 §3.7），以常量占位待接线。
 */
import { useEffect, useState } from "react";
import { Activity, Bot, Layers, Settings2, Wrench } from "lucide-react";

import { ChunkBoundaryViewer } from "@/components/ChunkBoundaryViewer";
import { CleaningDiffCard } from "@/components/CleaningDiffCard";
import { CommunitySummaryBrowser } from "@/components/CommunitySummaryBrowser";
import { EmbeddingProbeCard } from "@/components/EmbeddingProbeCard";
import { HotReloadDemoCard } from "@/components/HotReloadDemoCard";
import { IkAnalyzePlayground } from "@/components/IkAnalyzePlayground";
import { IngestionPanel } from "@/components/IngestionPanel";
import { ParsingPreviewPanel } from "@/components/ParsingPreviewPanel";
import { PointInspector } from "@/components/PointInspector";
import { RerankCompareView } from "@/components/RerankCompareView";
import { RetrievalDebugConsole } from "@/components/RetrievalDebugConsole";
import { getReady } from "@/api/health";
import type { HealthComponent, ReadyResponse } from "@/api/health";
import { useAuthStore } from "@/stores/authStore";
import { useConfigStore } from "@/stores/configStore";

type SectionKey = "overview" | "pipeline" | "retrieval" | "agent" | "system";

const SECTIONS: { key: SectionKey; label: string; icon: typeof Activity }[] = [
  { key: "overview", label: "总览", icon: Activity },
  { key: "pipeline", label: "管道", icon: Wrench },
  { key: "retrieval", label: "检索", icon: Layers },
  { key: "agent", label: "Agent", icon: Bot },
  { key: "system", label: "系统", icon: Settings2 },
];

/** 调试分区显隐占位（TODO: 随 02 §3.7 暴露 debug_enabled 后接线）。 */
const DEBUG_SECTIONS_VISIBLE = true;

/** 组件状态色（up 绿 / degraded 橙 / down 红）。 */
const STATUS_COLOR: Record<HealthComponent["status"], string> = {
  up: "bg-green-500",
  degraded: "bg-orange-500",
  down: "bg-red-500",
};

/** 区块标题 + 单元号注释的通用卡片头。 */
function CardHead({ title, unit }: { title: string; unit: string }) {
  return (
    <div className="mb-3 flex items-baseline gap-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      <span className="text-[11px] text-neutral-400">{unit}</span>
    </div>
  );
}

/** 占位说明条（未落地单元）。 */
function Pending({ text }: { text: string }) {
  return <p className="text-xs text-neutral-400">{text}</p>;
}

/** HealthOverview（06 §8.1）：GET /ready 七组件聚合卡。 */
function HealthOverview() {
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getReady()
      .then(setReady)
      .catch(() => setFailed(true));
  }, []);

  if (failed) return <Pending text="/ready 不可达（后端未就绪）" />;
  if (!ready) return <Pending text="加载中…" />;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
      {Object.entries(ready.components).map(([name, c]) => (
        <div
          key={name}
          className="rounded-xl border border-neutral-200 bg-white px-3 py-2.5 dark:border-neutral-700 dark:bg-neutral-800"
        >
          <div className="flex items-center gap-1.5">
            <span className={`inline-block h-2 w-2 rounded-full ${STATUS_COLOR[c.status]}`} />
            <span className="text-xs font-medium">{name}</span>
          </div>
          <p className="mt-1 text-[11px] text-neutral-400">
            {c.status}
            {typeof c.latency_ms === "number" ? ` · ${c.latency_ms}ms` : ""}
          </p>
        </div>
      ))}
    </div>
  );
}

/** AgentFlowOverview（06 §8.1）：五节点图只读画布（flowchart BUI 落点占位）。 */
function AgentFlowOverview() {
  const steps = [
    "planner",
    "tool_router",
    "reflector",
    "generator",
    "self_correction",
  ];
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs">
      {steps.map((s, i) => (
        <span key={s} className="flex items-center gap-1.5">
          <span className="rounded-full border border-neutral-200 bg-white px-2.5 py-1 font-medium dark:border-neutral-700 dark:bg-neutral-800">
            {s}
          </span>
          {i < steps.length - 1 ? <span className="text-neutral-400">→</span> : null}
        </span>
      ))}
      <span className="ml-2 text-[11px] text-neutral-400">（回环：reflector→planner ≤3 轮；M3）</span>
    </div>
  );
}

export default function AdminPage() {
  const user = useAuthStore((s) => s.user);
  const profile = useConfigStore((s) => s.profile);
  const [section, setSection] = useState<SectionKey>("overview");

  if (user?.role !== "admin") {
    return (
      <p className="p-6 text-sm text-neutral-500">AUTH_403_FORBIDDEN：仅 admin 可见</p>
    );
  }

  return (
    <div className="flex h-screen">
      {/* 左侧分区导航（sidebar-nav BUI 落点） */}
      <nav className="w-44 shrink-0 border-r p-3">
        <h1 className="mb-3 px-2 text-sm font-semibold">管理台</h1>
        {SECTIONS.map((s) => {
          const Icon = s.icon;
          const hidden =
            !DEBUG_SECTIONS_VISIBLE &&
            (s.key === "pipeline" || s.key === "retrieval" || s.key === "agent");
          if (hidden) return null;
          return (
            <button
              key={s.key}
              className={`mb-0.5 flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm ${
                section === s.key
                  ? "bg-neutral-200/70 font-medium dark:bg-neutral-700/70"
                  : "text-neutral-600 hover:bg-neutral-200/40 dark:text-neutral-300 dark:hover:bg-neutral-800/60"
              }`}
              onClick={() => setSection(s.key)}
            >
              <Icon size={14} /> {s.label}
            </button>
          );
        })}
      </nav>

      {/* 右侧卡片流（锚点滚动由分区切换承载） */}
      <main className="min-w-0 flex-1 overflow-y-auto p-6">
        {section === "overview" ? (
          <div className="space-y-8">
            <div>
              <CardHead title="存储与依赖健康" unit="GET /ready · 单元 10.1/9.2" />
              <HealthOverview />
            </div>
            <div>
              <CardHead title="运行 Profile" unit="GET /config/public · 单元 9.2" />
              <p className="text-xs text-neutral-500">当前 Profile：{profile || "未加载"}</p>
            </div>
          </div>
        ) : null}

        {section === "pipeline" ? (
          <div className="max-w-3xl space-y-8">
            <div>
              <CardHead title="采集" unit="单元 1.1" />
              <IngestionPanel />
            </div>
            <div>
              <CardHead title="解析预览" unit="单元 1.2" />
              <ParsingPreviewPanel />
            </div>
            <div>
              <CardHead title="清洗对比" unit="单元 1.3" />
              <CleaningDiffCard />
            </div>
            <div>
              <CardHead title="分块边界" unit="单元 2.1" />
              <ChunkBoundaryViewer />
            </div>
          </div>
        ) : null}

        {section === "retrieval" ? (
          <div className="max-w-3xl space-y-8">
            <div>
              <CardHead title="向量探针" unit="单元 2.3" />
              <EmbeddingProbeCard />
            </div>
            <div>
              <CardHead title="检索调试台" unit="单元 3.1-4.2" />
              <PointInspector />
              <IkAnalyzePlayground />
              <RetrievalDebugConsole />
              <RerankCompareView />
              <HotReloadDemoCard />
            </div>
          </div>
        ) : null}

        {section === "agent" ? (
          <div className="max-w-3xl space-y-8">
            <div>
              <CardHead title="Agent 流水线总览" unit="单元 5.1" />
              <AgentFlowOverview />
            </div>
            <div>
              <CardHead title="运行检视" unit="单元 5.2-7.1" />
              <Pending text="AgentStateInspector / PlanStepsList / FanoutStatusView / ReflectorFeedbackView / RegenerationNotice / FaithfulnessBadge（SSE 聚合，随 10.3 接线）…" />
            </div>
          </div>
        ) : null}

        {section === "system" ? (
          <div className="max-w-3xl space-y-8">
            <div>
              <CardHead title="社区摘要浏览" unit="单元 2.6" />
              <CommunitySummaryBrowser />
            </div>
            <div>
              <CardHead title="审核队列 / 任务 / golden 导出" unit="单元 2.4/7.2/10.6" />
              <Pending text="ReviewQueuePanel / TaskProgressPanel / GoldenExportButton / 缓存清理与索引重建卡（02 §3.10）…" />
            </div>
          </div>
        ) : null}
      </main>
    </div>
  );
}
