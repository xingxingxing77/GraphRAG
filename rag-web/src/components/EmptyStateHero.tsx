/**
 * EmptyStateHero（06 §8 v1.3 + 14 适配）：Chat 空态主区。
 * 结构："hi GraphRAG" 文案（无 logo 图片资源，J24 落地方案 §0）+
 * chips（TierSelector，意图定档；模型选择由输入框内置 ModelPicker 承载）+
 * 居中大输入框（prompt-bar 落点，Enter 发送 / Shift+Enter 换行；自带
 * @数据源 / /命令 / 模型选择器 / 语音 / + 附件能力，14 接入）+ 建议卡 ×3
 * （recommendation-card 落点，点击回填）。同时导出 Composer 供
 * ChatPage 会话态底部停靠输入条复用（双态同构，06 §7）。
 */
import PromptBar from "@/components/bui/prompt-bar";
import { useChatStore } from "@/stores/chatStore";

const CHIP_SELECT =
  "rounded-chip border border-line bg-field px-3 py-1 text-xs text-ink-2 outline-none hover:border-line-strong";

/** Composer Props（已迁移至 prompt-bar，保留签名以兼容 Chat.tsx 旧 import）。 */
export interface ComposerProps {
  /** 停靠条紧凑形态（会话态） */
  compact?: boolean;
  /** 提交回调（父级编排 sendMessage） */
  onSubmit(query: string): void;
}

/**
 * 会话态底部停靠输入条（已用 prompt-bar 实现，14 接入）。
 *
 * @param props - 见 ComposerProps。
 * @returns PromptBar 实例。
 */
export function Composer({ onSubmit, compact }: ComposerProps) {
  return (
    <PromptBar
      demo={false}
      variant="Pill"
      tall={!compact}
      placeholder="输入你的问题…"
      onSend={onSubmit}
    />
  );
}

/** EmptyStateHero Props。 */
export interface EmptyStateHeroProps {
  /** 建议问题列表（点击回填后由用户发送） */
  suggestions: string[];
  /** 提交回调 */
  onSubmit(query: string): void;
}

/** 默认建议问题（HowToCook 语料域，随 configStore 扩展可配置）。 */
const DEFAULT_SUGGESTIONS = [
  "清蒸鲈鱼怎么做？",
  "不含海鲜的高蛋白菜有哪些？",
  "推荐一道适合新手的快手菜",
];

/**
 * 渲染空态主区（hi GraphRAG + chips + 大输入框 + 建议卡）。
 *
 * @param props - 见 EmptyStateHeroProps。
 * @returns 空态主区元素。
 */
export function EmptyStateHero({ suggestions, onSubmit }: EmptyStateHeroProps) {
  const activeTier = useChatStore((s) => s.activeTier);
  const setActiveTier = useChatStore((s) => s.setActiveTier);

  return (
    <div className="flex h-full flex-col items-center justify-center px-6">
      {/* 标语文案（无 logo / 无版本徽章） */}
      <h1 className="mb-8 text-2xl font-semibold tracking-tight text-ink">hi GraphRAG</h1>

      {/* chips：仅档位（模型选择由输入框内置 ModelPicker 承载，输入框不受影响） */}
      <div className="mb-4 flex items-center gap-2">
        <select
          className={CHIP_SELECT}
          value={activeTier}
          onChange={(e) =>
            setActiveTier(e.target.value as "auto" | "fast" | "standard" | "deep")
          }
          aria-label="响应档位"
        >
          <option value="auto">auto（意图定档）</option>
          <option value="fast">fast</option>
          <option value="standard">standard</option>
          <option value="deep">deep</option>
        </select>
      </div>

      {/* 居中大输入框（prompt-bar tall 模式，demo=false 时 w-full 适配页面宽度） */}
      <div className="w-full max-w-3xl">
        <PromptBar
          demo={false}
          tall
          variant="Rounded"
          placeholder="输入你的问题…"
          onSend={onSubmit}
        />
      </div>

      {/* 建议卡（recommendation-card 落点） */}
      <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
        {(suggestions.length > 0 ? suggestions : DEFAULT_SUGGESTIONS).map((s) => (
          <button
            key={s}
            className="rounded-card border border-line bg-surface px-3.5 py-2 text-xs text-ink-2 shadow-card transition-colors hover:border-line-strong hover:text-ink-2"
            onClick={() => onSubmit(s)}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
