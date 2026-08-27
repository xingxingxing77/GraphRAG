/**
 * ParticleOrb —— 登录页粒子球背景（docs/登录页粒子球落地方案.md §3）。
 *
 * 纯 Canvas 2D + rAF，零依赖（J24/08 R4 合规）。三层粒子：
 * 球壳（斐波那契分布、极点加密）+ 赤道波形带 + 球外环境散点；
 * 光标经逆旋转映射进模型空间形成真 3D 位移场（推开→悬浮→弱回弹）。
 * 常量 1:1 取自参考实现；prefers-reduced-motion 时仅渲染静帧。
 */
import { useEffect, useRef } from "react";

export interface ParticleOrbProps {
  /** 球心锚定元素（默认定位父容器）；球心 = 锚点中心 + 球高 38% 下移 */
  anchorRef?: React.RefObject<HTMLElement | null>;
  /** 附加 className（定位容器须为 relative/absolute，组件根为 absolute 铺底） */
  className?: string;
}

interface Displacement {
  dx: number;
  dy: number;
  dz: number;
  vx: number;
  vy: number;
  vz: number;
}

interface ShellParticle extends Displacement {
  type: 0;
  phi: number;
  lat: number;
  phase: number;
}

interface WaveParticle extends Displacement {
  type: 1;
  phi: number;
  latBase: number;
  jphi: number;
  phase: number;
}

type OrbParticle = ShellParticle | WaveParticle;

interface Stray {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  base: number;
  tw: number;
  tws: number;
}

const GOLDEN = 2.399963229728653;

/** 波形函数：球壳闪烁与赤道波形带共用（方案 §3） */
function wave(phi: number, t: number): number {
  return (
    Math.sin(6 * phi + t) * 0.5 +
    Math.sin(11 * phi + 1.7 * t) * 0.3 +
    Math.sin(3 * phi - 0.6 * t) * 0.2
  );
}

export default function ParticleOrb({ anchorRef, className }: ParticleOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvasNode = canvasRef.current;
    const wrapNode = canvasNode?.parentElement;
    const ctxNode = canvasNode?.getContext("2d") ?? null;
    if (!canvasNode || !wrapNode || !ctxNode) return;
    const canvas: HTMLCanvasElement = canvasNode;
    const wrap: HTMLElement = wrapNode;
    const ctx: CanvasRenderingContext2D = ctxNode;
    const stage: HTMLElement | null = wrap.parentElement;
    const anchor: HTMLElement | null = anchorRef?.current ?? stage;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const small = Math.min(window.innerWidth, window.innerHeight) < 700;

    // ── 常量表（1:1，见方案 §3）──
    const SHELL_COUNT = small ? 1400 : 2600;
    const WAVE_COUNT = small ? 1000 : 1900;
    const STRAY_COUNT = small ? 50 : 90;
    const ROT_SPEED = 0.00008;
    const TILT = 0.32;
    const WAVE_BAND = 0.095;
    const WAVE_LAT = -0.5;
    const WAVE_AMP = 0.62;
    const SHELL_SHIMMER = 0.02;
    const FLOW_SPEED = 0.0009;
    const STRAY_DRIFT = 0.05;
    const STRAY_EXCL = 1.2;
    const MOUSE_R = 0.32;
    const PUSH_K = 0.016;
    const RETURN = 0.0025;
    const DAMP = 0.95;
    const MOUSE_LERP = 0.07;

    let W = 0;
    let H = 0;
    let CX = 0;
    let CY = 0;
    let RADIUS = 0;
    let CAM = 0;
    let particles: OrbParticle[] = [];
    let strays: Stray[] = [];
    const mouse = { x: -9999, y: -9999, tx: -9999, ty: -9999 };

    /** 沿 offsetTop 链求 el 相对 ancestor 的纵偏移（忽略 transform） */
    function offsetTopWithin(el: HTMLElement, ancestor: HTMLElement | null): number {
      let y = 0;
      let node: HTMLElement | null = el;
      while (node && node !== ancestor) {
        y += node.offsetTop;
        node = node.offsetParent as HTMLElement | null;
      }
      return y;
    }

    /** 球心锚定：球心 = 锚点中心 + 球高 38% 下移。
     * 球心在 wrap 内居中，所以 wrap.style.top = 锚点中心 + 球高 38% - wrap.height/2
     * （即 offset = wrap.height × (0.38 - 0.5) = -wrap.height × 0.12）。 */
    function positionOrb(): void {
      if (!anchor || !stage) return;
      const centerY = offsetTopWithin(anchor, stage) + anchor.offsetHeight / 2;
      const offset = wrap.offsetHeight * (0.38 - 0.5);
      wrap.style.top = `${centerY + offset}px`;
    }

    function resize(): void {
      const dpr = window.devicePixelRatio || 1;
      W = canvas.clientWidth;
      H = canvas.clientHeight;
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      CX = W / 2;
      CY = H / 2;
      RADIUS = Math.min(W, H) * 0.255;
      CAM = RADIUS * 3.0;
      positionOrb();
      buildStrays();
    }

    function build(): void {
      const shell: ShellParticle[] = [];
      for (let i = 0; i < SHELL_COUNT; i++) {
        const u = 1 - (i / (SHELL_COUNT - 1)) * 2;
        const y = Math.sign(u) * Math.pow(Math.abs(u), 0.6);
        shell.push({
          type: 0,
          phi: i * GOLDEN,
          lat: Math.asin(y),
          phase: Math.random() * Math.PI * 2,
          dx: 0, dy: 0, dz: 0, vx: 0, vy: 0, vz: 0,
        });
      }
      const band: WaveParticle[] = [];
      for (let i = 0; i < WAVE_COUNT; i++) {
        band.push({
          type: 1,
          phi: (i / WAVE_COUNT) * Math.PI * 2,
          latBase: WAVE_LAT + (Math.random() - 0.5) * 2 * WAVE_BAND,
          jphi: (Math.random() - 0.5) * 0.05,
          phase: Math.random() * Math.PI * 2,
          dx: 0, dy: 0, dz: 0, vx: 0, vy: 0, vz: 0,
        });
      }
      particles = [...shell, ...band];
    }

    function buildStrays(): void {
      const next: Stray[] = [];
      const excl = RADIUS * STRAY_EXCL;
      for (let i = 0; i < STRAY_COUNT; i++) {
        let x = 0;
        let y = 0;
        let tries = 0;
        do {
          x = Math.random() * W;
          y = Math.random() * H;
        } while (Math.hypot(x - CX, y - CY) < excl && ++tries < 24);
        next.push({
          x,
          y,
          vx: (Math.random() - 0.5) * 2 * STRAY_DRIFT,
          vy: (Math.random() - 0.5) * 2 * STRAY_DRIFT,
          size: 1.1 + Math.random() * 1.6,
          base: 0.4 + Math.random() * 0.5,
          tw: Math.random() * Math.PI * 2,
          tws: 0.0006 + Math.random() * 0.0016,
        });
      }
      strays = next;
    }

    let rafId = 0;

    function loop(now: number): void {
      mouse.x += (mouse.tx - mouse.x) * MOUSE_LERP;
      mouse.y += (mouse.ty - mouse.y) * MOUSE_LERP;

      const ang = now * ROT_SPEED;
      const cosY = Math.cos(ang);
      const sinY = Math.sin(ang);
      const cosX = Math.cos(TILT);
      const sinX = Math.sin(TILT);
      const t = now * FLOW_SPEED;

      // 光标映射到球面正面半球，再逆旋转入单位球局部空间（真 3D 推力）
      const active = mouse.tx > -9000;
      let mlx = 0;
      let mly = 0;
      let mlz = 0;
      if (active) {
        const mvx = (mouse.x - CX) / RADIUS;
        const mvy = (mouse.y - CY) / RADIUS;
        const r2 = mvx * mvx + mvy * mvy;
        const mvz = r2 < 1 ? -Math.sqrt(1 - r2) : 0;
        const yy = mvy * cosX + mvz * sinX;
        const z1 = -mvy * sinX + mvz * cosX;
        mlx = mvx * cosY - z1 * sinY;
        mly = yy;
        mlz = mvx * sinY + z1 * cosY;
      }

      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = "lighter";

      for (let k = 0; k < particles.length; k++) {
        const p = particles[k] as OrbParticle;
        let hx: number;
        let hy: number;
        let hz: number;
        let crest = 0;

        if (p.type === 0) {
          const lat = p.lat + wave(p.phi + p.phase, t) * SHELL_SHIMMER;
          const cl = Math.cos(lat);
          hx = Math.cos(p.phi) * cl;
          hy = Math.sin(lat);
          hz = Math.sin(p.phi) * cl;
        } else {
          const phi = p.phi + p.jphi;
          crest = wave(phi, t + p.phase * 0.2);
          const lat = p.latBase + crest * WAVE_AMP * WAVE_BAND * 3;
          const cl = Math.cos(lat);
          hx = Math.cos(phi) * cl;
          hy = Math.sin(lat);
          hz = Math.sin(phi) * cl;
        }

        // 3D 位移物理（单位球空间）
        const cx = hx + p.dx;
        const cy = hy + p.dy;
        const cz = hz + p.dz;
        if (active) {
          const ddx = cx - mlx;
          const ddy = cy - mly;
          const ddz = cz - mlz;
          const dist = Math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz);
          if (dist < MOUSE_R && dist > 1e-4) {
            const force = (MOUSE_R - dist) * PUSH_K;
            const inv = 1 / dist;
            p.vx += ddx * inv * force;
            p.vy += ddy * inv * force;
            p.vz += ddz * inv * force;
          }
        }
        p.vx += -p.dx * RETURN;
        p.vy += -p.dy * RETURN;
        p.vz += -p.dz * RETURN;
        p.vx *= DAMP;
        p.vy *= DAMP;
        p.vz *= DAMP;
        p.dx += p.vx;
        p.dy += p.vy;
        p.dz += p.vz;

        const lx = (hx + p.dx) * RADIUS;
        const ly = (hy + p.dy) * RADIUS;
        const lz = (hz + p.dz) * RADIUS;

        // 绕 Y 旋转 → 绕 X 倾斜 → 透视投影
        const x1 = lx * cosY + lz * sinY;
        const z1 = -lx * sinY + lz * cosY;
        const y1 = ly * cosX - z1 * sinX;
        const z2 = ly * sinX + z1 * cosX;

        const scale = CAM / (CAM + z2);
        const sx = CX + x1 * scale;
        const sy = CY + y1 * scale;

        const depth = (1 - z2 / RADIUS) / 2; // 0 背面 .. 1 正面
        let size: number;
        let alpha: number;
        if (p.type === 0) {
          const pole = Math.abs(hy);
          size = (0.55 + depth * 0.9) * scale;
          alpha = Math.min(1, 0.06 + depth * depth * 0.8 + pole * pole * 0.24);
        } else {
          const c = (crest + 1) / 2;
          size = (0.85 + c * 1.55) * scale;
          alpha = Math.min(1, (0.4 + c * 0.6) * (0.16 + depth * 0.84));
        }
        ctx.fillStyle = `rgba(255, 255, 255, ${alpha.toFixed(3)})`;
        ctx.fillRect(sx, sy, size, size);
      }

      // 环境散点：球外 2D 漂移 + 闪烁
      const sExcl = RADIUS * STRAY_EXCL;
      const sBand = RADIUS * 0.22;
      for (let s = 0; s < strays.length; s++) {
        const p = strays[s];
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0) p.x += W;
        else if (p.x > W) p.x -= W;
        if (p.y < 0) p.y += H;
        else if (p.y > H) p.y -= H;
        const dist = Math.hypot(p.x - CX, p.y - CY);
        if (dist < sExcl) continue;
        const edge = Math.min(1, (dist - sExcl) / sBand);
        const twinkle = 0.6 + 0.4 * Math.sin(now * p.tws + p.tw);
        const alpha = p.base * twinkle * edge;
        if (alpha <= 0.01) continue;
        ctx.fillStyle = `rgba(255, 255, 255, ${alpha.toFixed(3)})`;
        ctx.fillRect(p.x, p.y, p.size, p.size);
      }

      ctx.globalCompositeOperation = "source-over";
      if (!reduce) rafId = requestAnimationFrame(loop);
    }

    function onMove(clientX: number, clientY: number): void {
      const r = canvas.getBoundingClientRect();
      mouse.tx = clientX - r.left;
      mouse.ty = clientY - r.top;
    }
    const onMouseMove = (e: MouseEvent): void => onMove(e.clientX, e.clientY);
    const onMouseLeave = (): void => {
      mouse.tx = -9999;
      mouse.ty = -9999;
    };
    const onTouchMove = (e: TouchEvent): void => onMove(e.touches[0].clientX, e.touches[0].clientY);
    const onTouchEnd = (): void => {
      mouse.tx = -9999;
      mouse.ty = -9999;
    };

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseleave", onMouseLeave);
    document.addEventListener("touchmove", onTouchMove, { passive: true });
    document.addEventListener("touchend", onTouchEnd);
    window.addEventListener("resize", resize);
    window.addEventListener("load", positionOrb);
    if (document.fonts?.ready) void document.fonts.ready.then(positionOrb);
    const timers = [300, 900, 1600].map((d) => window.setTimeout(positionOrb, d));

    resize();
    build();
    if (reduce) {
      loop(0);
    } else {
      rafId = requestAnimationFrame(loop);
    }

    return () => {
      cancelAnimationFrame(rafId);
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseleave", onMouseLeave);
      document.removeEventListener("touchmove", onTouchMove);
      document.removeEventListener("touchend", onTouchEnd);
      window.removeEventListener("resize", resize);
      window.removeEventListener("load", positionOrb);
      timers.forEach((id) => window.clearTimeout(id));
    };
    // 常量在挂载时读取一次；anchorRef 为稳定引用，动态改 props 不重建循环
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

}, []);

  return (
    <div
      aria-hidden
      className={`pointer-events-none absolute left-1/2 top-1/2 z-0 w-[clamp(700px,70vw,1120px)] h-[clamp(700px,70vw,1120px)] select-none ${className ?? ""}`}
      style={{ transform: "translate(-50%, -50%) scale(1.08)", mixBlendMode: "screen" }}
    >
      <canvas
        ref={canvasRef}
        className="absolute left-1/2 top-1/2 block h-[180%] w-[180%]"
        style={{ transform: "translate(-50%, -50%)" }}
      />
    </div>
  );
}
