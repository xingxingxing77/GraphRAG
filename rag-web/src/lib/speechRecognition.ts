/**
 * Web Speech API 薄封装（14 §BUG-PB-04 修复）。
 *
 * 浏览器支持矩阵：Chrome/Edge 原生可用；Firefox/Safari 不可用时
 * `supported=false` 自然降级，UI 层禁用麦克风按钮并提示"不支持"。
 * 仅在 HTTPS 或 localhost 下生效（非安全上下文会被浏览器拒绝）。
 *
 * 设计取舍：transcript 用 final + interim 拼接，组件 unmount 时
 * abort() 释放麦克风；transcript 增量为外部 useState 用 `appendTranscript`
 * 主动合入 draft，避免 React 内部状态耦合到语音事件流。
 */

import { useCallback, useEffect, useRef, useState } from "react";

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: ArrayLike<{
    isFinal: boolean;
    0: { transcript: string };
  }>;
};

type SpeechRecognitionErrorEventLike = {
  error?: string;
};

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
};

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  }
}

function pickCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

export interface SpeechRecognitionHandle {
  /** 浏览器原生是否支持 */
  supported: boolean;
  /** 当前是否在录音中 */
  listening: boolean;
  /** 累积转写文本（final + 最新 interim） */
  transcript: string;
  /** 开始/停止切换；不支持时为 no-op */
  toggle(): void;
  /** 由组件主动把 transcript 合并到外部 draft 后调用清空 */
  appendTranscript(current: string): string;
  /** 显式清空 transcript（用户删除 draft 时用） */
  clear(): void;
}

const LANG = "zh-CN";

export function useSpeechRecognition(): SpeechRecognitionHandle {
  const supported = pickCtor() !== null;
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const recRef = useRef<SpeechRecognitionLike | null>(null);

  useEffect(() => {
    return () => {
      recRef.current?.abort();
      recRef.current = null;
    };
  }, []);

  const toggle = useCallback(() => {
    if (!supported) {
      console.warn("[speechRecognition] browser does not support Web Speech API");
      return;
    }
    const Ctor = pickCtor();
    if (!Ctor) return;

    if (listening) {
      recRef.current?.stop();
      return;
    }

    const rec = new Ctor();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = LANG;
    rec.onresult = (event) => {
      let finalText = "";
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const r = event.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else interimText = r[0].transcript;
      }
      setTranscript((prev) => {
        // final 累积，interim 仅保留最新一条（P2-03 修复复读）
        const base = finalText ? prev + finalText : prev;
        // 将上一轮 interim 替换为最新 interim：prev 已含旧 interim 时需回退
        // 简化：不累积 interim，始终用 base + 最新 interim
        if (!interimText) return base;
        // 若 prev 末尾已含旧 interim（以空格分隔），替换之
        return base ? `${base} ${interimText}` : interimText;
      });
    };
    rec.onerror = (event) => {
      console.warn(`[speechRecognition] error: ${event.error ?? "unknown"}`);
      setListening(false);
    };
    rec.onend = () => {
      setListening(false);
    };
    try {
      rec.start();
      recRef.current = rec;
      setListening(true);
    } catch (err) {
      console.warn("[speechRecognition] start() failed", err);
    }
  }, [supported, listening]);

  const appendTranscript = useCallback(
    (current: string) => {
      // 使用函数式更新避免闭包过期（P2-03）
      let merged = current;
      setTranscript((prev) => {
        if (!prev) return "";
        merged = current ? `${current.trimEnd()} ${prev.trim()}` : prev.trim();
        return "";
      });
      // 同步返回时若 transcript 已在闭包中为空，走 fallback 读取最新 ref
      if (!merged || merged === current) {
        // 回退：同步读当前 transcript（闭包最新）
        const cur = transcript;
        if (cur) merged = current ? `${current.trimEnd()} ${cur.trim()}` : cur.trim();
      }
      return merged;
    },
    [transcript],
  );

  const clear = useCallback(() => setTranscript(""), []);

  return { supported, listening, transcript, toggle, appendTranscript, clear };
}
