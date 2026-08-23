/**
 * EmptyStateHero（06 §8 v1.3）：Chat 空态主区。
 * 结构："hi GraphRAG" 文案（无 logo 图片资源，J24 落地方案 §0）+
 * chips（TierSelector/ModelPicker，枚举来自 configStore）+ 居中大输入框
 * （chat-composer 落点，Enter 发送 / Shift+Enter 换行）+ 建议卡 ×3
 * （recommendation-card 落点，点击回填）。同时导出 Composer 供
 * ChatPage 会话态底部停靠输入条复用（双态同构，06 §7）。
 */
import { useState } from "react";
import { ArrowUp } from "lucide-react";

import { useChatStore } from "@/stores/chatStore";
import { useConfigStore } from "@/stores/configStore";

/** 输入框样式（空态大框与会话态停靠条共用，compact 收窄）。 */
const COMPOSER_BOX =
  "w-full rounded-2xl border border-neutral-200 bg-white shadow-sm transition-colors focus-within:border-neutral-300 dark:border-neutral-700 dark:bg-neutral-800";
const COMPOSER_TEXTAREA =
  "w-full resize-none bg-transparent text-sm outline-none placeholder:text-neutral-400";
const CHIP_SELECT =
  "rounded-full border border-neutral-200 bg-white px-3 py-1 text-xs text-neutral-600 outline-none hover:border-neutral-300 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-300";

/** Composer Props。 */
export interface ComposerProps {
  /** 停靠条紧凑形态（会话态） */
  compact?: boolean;
  /** 提交回调（父级编排 sendMessage） */
  onSubmit(query: string): void;
}

/**
 * 输入区（空态居中大框 / 会话态底部停靠条，双态同构）。
 *
 * @param props - 见 ComposerProps。
 * @returns 输入区元素。
 */
export function Composer({ compact = false, onSubmit }: ComposerProps) {
  const [value, setValue] = useState("");

  /** 提交（空串拦截；提交后清空）。 */
  function submit() {
    const q = value.trim();
    if (!q) return;
    setValue("");
    onSubmit(q);
  }

  return (
    <div className={COMPOSER_BOX}>
      <textarea
        rows={compact ? 1 : 3}
        className={`${COMPOSER_TEXTAREA} ${compact ? "px-3.5 pb-1 pt-2.5" : "px-4 pb-1 pt-3.5"}`}
        placeholder="输入你的问题…"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <div className={`flex items-center ${compact ? "px-2.5 pb-2" : "px-3 pb-2.5"}`}>
        <span className="flex-1" />
        <button
          className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-500 text-white transition-colors hover:bg-blue-600 disabled:opacity-40"
          disabled={!value.trim()}
          onClick={submit}
          aria-label="发送"
        >
          <ArrowUp size={15} />
        </button>
      </div>
    </div>
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
  const models = useConfigStore((s) => s.models);
  const [model, setModel] = useState<string>("");

  return (
    <div className="flex h-full flex-col items-center justify-center px-6">
      {/* 标语文案（无 logo / 无版本徽章） */}
      <h1 className="mb-8 text-2xl font-semibold tracking-tight">hi GraphRAG</h1>

      {/* chips：档位 + 模型（prompt-bar 落点） */}
      <div className="mb-4 flex items-center gap-2">
        <select
          className={CHIP_SELECT}
          value={activeTier}
          onChange={(e) => setActiveTier(e.target.value as "fast" | "standard" | "deep")}
          aria-label="响应档位"
        >
          <option value="fast">fast</option>
          <option value="standard">standard</option>
          <option value="deep">deep</option>
        </select>
        <select
          className={CHIP_SELECT}
          value={model}
          onChange={(e) => setModel(e.target.value)}
          aria-label="模型"
        >
          <option value="">默认模型</option>
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {/* 居中大输入框 */}
      <div className="w-full max-w-2xl">
        <Composer onSubmit={onSubmit} />
      </div>

      {/* 建议卡（recommendation-card 落点） */}
      <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
        {(suggestions.length > 0 ? suggestions : DEFAULT_SUGGESTIONS).map((s) => (
          <button
            key={s}
            className="rounded-xl border border-neutral-200 bg-white px-3.5 py-2 text-xs text-neutral-600 shadow-sm transition-colors hover:border-neutral-300 hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-300 dark:hover:bg-neutral-700"
            onClick={() => onSubmit(s)}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
