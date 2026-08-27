/**
 * 打字机渲染 Hook（06 §6，M1/J20）。
 * rAF 分片逐字；fast 档不走本 Hook（逐 token 直渲）。
 * 组件卸载即完成全文，防截断；提供 skip 立即显示全部（无障碍）。
 */
import { useEffect, useRef, useState } from "react";

export function useTypewriter(target: string | null, cps = 48) {
  const [shown, setShown] = useState("");
  const targetRef = useRef(target);

  useEffect(() => {
    targetRef.current = target;
    if (!target) {
      setShown("");
      return;
    }
    let i = 0;
    let last = performance.now();
    let acc = 0;
    let raf = 0;
    const step = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      acc += dt * cps;
      const advance = Math.floor(acc);
      if (advance > 0) {
        acc -= advance;
        i = Math.min(target.length, i + advance);
        setShown(target.slice(0, i));
      }
      if (i < target.length) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      // 卸载时若未完成则快进至全文，避免截断（P2-02）
      if (targetRef.current && i < targetRef.current.length) {
        setShown(targetRef.current);
      }
    };
  }, [target, cps]);

  return {
    shown,
    done: !!target && shown.length === target.length,
    skip: () => setShown(target ?? ""),
  };
}
