/**
 * 打字机渲染 Hook（06 §6，M1/J20）。
 * rAF 分片逐字；fast 档不走本 Hook（逐 token 直渲）。
 * 组件卸载即完成全文，防截断；提供 skip 立即显示全部（无障碍）。
 */
import { useEffect, useState } from "react";

export function useTypewriter(target: string | null, cps = 48) {
  const [shown, setShown] = useState("");

  useEffect(() => {
    if (!target) return;
    let i = 0;
    let last = performance.now();
    let raf = 0;
    const step = (now: number) => {
      i = Math.min(target.length, i + Math.floor(((now - last) / 1000) * cps));
      setShown(target.slice(0, i));
      last = now;
      if (i < target.length) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, cps]);

  return {
    shown,
    done: !!target && shown.length === target.length,
    skip: () => setShown(target ?? ""),
  };
}
