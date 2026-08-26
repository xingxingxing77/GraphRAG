/**
 * FaithfulnessBadge（06 §8，7.1）：deep 档忠实度校验通过标识
 * （SSE updates.self_correction.faithfulness_score）。
 */
export function FaithfulnessBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  return (
    <span className="ml-2 inline-flex items-center gap-1 rounded-chip bg-green-tint px-2 py-0.5 text-[10px] text-green">
      已复核 {pct}%
    </span>
  );
}
