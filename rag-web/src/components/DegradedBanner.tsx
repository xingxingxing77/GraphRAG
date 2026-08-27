/**
 * DegradedBanner（06 §8/§9）：X-Degraded 七枚举常驻横幅。
 * 文案与 06 §9 逐值对齐（08 R1 反向校验覆盖 02 §2.4 全枚举）；
 * reasons 为空不渲染。挂载于 ChatPage / GraphExplorer 顶部（06 §7 v1.3）。
 */
import { useChatStore } from "@/stores/chatStore";

/** 降级原因 → 用户文案（06 §9，禁止同义异名）。 */
const DEGRADED_TEXT: Record<string, string> = {
  "no-graph": "图谱检索不可用，已降级为向量检索",
  "no-rerank": "精排暂不可用",
  "llm-fallback": "已切换备用模型回答",
  "no-memory": "多轮上下文暂不可用",
  "no-cache": "缓存层不可用，已按未命中处理（问答不受影响，相似问题将重新计算）",
  "budget-exhausted": "复杂度超预算，答案可能不完整",
  "no-persistence": "对话未保存（存储暂不可用）",
};

/**
 * 渲染当前降级态横幅（多值逐条展示）。
 *
 * @returns 橙色常驻横幅；无降级时为 null。
 */
export function DegradedBanner() {
  const reasons = useChatStore((s) => s.degradedReasons);
  if (reasons.length === 0) return null;
  return (
    <div className="flex flex-col gap-0.5 border-b border-orange-200 bg-orange-50 px-4 py-2 dark:border-orange-900 dark:bg-orange-950/40">
      {reasons.map((r) => (
        <p key={r} className="text-xs text-orange-700 dark:text-orange-300">
          {DEGRADED_TEXT[r] ?? r}
        </p>
      ))}
    </div>
  );
}
