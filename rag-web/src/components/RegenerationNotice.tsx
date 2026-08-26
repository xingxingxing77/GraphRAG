/**
 * RegenerationNotice（06 §8，5.6）：SSE updates.generator(regenerated) 触发的
 * 「正在复核答案」重生成提示（M1 自校正重生成）。
 */
export function RegenerationNotice({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <span className="ml-2 inline-flex items-center gap-1 rounded-chip bg-accent-tint px-2 py-0.5 text-[10px] text-accent-ink">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
      正在复核答案
    </span>
  );
}
