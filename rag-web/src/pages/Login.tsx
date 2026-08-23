/**
 * Login 页（06 §7）：兑换 token（02 §3.1），成功入 authStore。
 * 视觉：暗色 + 粒子球背景（docs/登录页粒子球落地方案.md）；
 * 登录接真实 authStore.login；注册为 UI 占位（后端注册接口未实现，02 暂无该端点）。
 */
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import ParticleOrb from "@/components/fx/ParticleOrb";
import { useAuthStore } from "@/stores/authStore";

type TabKey = "login" | "register";

interface Msg {
  text: string;
  kind: "error" | "ok" | null;
}

const FIELD_INPUT =
  "w-full rounded-[10px] border border-white/[0.08] bg-white/[0.03] px-3.5 py-2.5 text-sm font-light text-neutral-200 outline-none transition-colors placeholder:text-neutral-600 focus:border-white/35 focus:bg-white/[0.05] focus:shadow-[0_0_0_1px_rgba(255,255,255,0.12),0_0_18px_rgba(255,255,255,0.08)]";
const FIELD_LABEL = "mb-1.5 block text-[11.5px] font-medium tracking-wider text-neutral-500";
const TAB_BASE =
  "flex-1 rounded-[10px] border py-2.5 text-[13px] font-semibold tracking-[4px] indent-4 transition-colors cursor-pointer";
const TAB_ACTIVE = "border-white/35 bg-white/[0.07] text-white shadow-[0_0_14px_rgba(255,255,255,0.10),inset_0_1px_0_rgba(255,255,255,0.10)]";
const TAB_IDLE = "border-white/[0.08] bg-white/[0.02] text-neutral-400 hover:text-neutral-200 hover:border-white/[0.14]";

export default function LoginPage() {
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();
  const cardRef = useRef<HTMLDivElement | null>(null);
  const [tab, setTab] = useState<TabKey>("login");

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginMsg, setLoginMsg] = useState<Msg>({ text: "", kind: null });
  const [busy, setBusy] = useState(false);

  const [regUsername, setRegUsername] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regConfirm, setRegConfirm] = useState("");
  const [regMsg, setRegMsg] = useState<Msg>({ text: "注册接口开发中，当前为界面预览", kind: null });

  async function onLoginSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (!username.trim() || !password) {
      setLoginMsg({ text: "请输入用户名和密码", kind: "error" });
      return;
    }
    setLoginMsg({ text: "", kind: null });
    setBusy(true);
    try {
      await login({ grant_type: "password", username, password });
      navigate("/chat");
    } catch {
      setLoginMsg({ text: "凭证错误，请重试（AUTH_400_BAD_CREDENTIALS）", kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  function onRegisterSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!regUsername.trim() || !regPassword || !regConfirm) {
      setRegMsg({ text: "请填写完整的注册信息", kind: "error" });
      return;
    }
    if (regPassword.length < 8) {
      setRegMsg({ text: "密码长度至少 8 位", kind: "error" });
      return;
    }
    if (regPassword !== regConfirm) {
      setRegMsg({ text: "两次输入的密码不一致", kind: "error" });
      return;
    }
    // 后端注册接口（02 契约扩展）就绪后，在此替换为真实调用
    setRegMsg({ text: "注册功能即将上线，敬请期待", kind: "ok" });
  }

  const msgClass = (m: Msg) =>
    `min-h-[18px] mt-2.5 px-0.5 text-xs ${m.kind === "error" ? "text-red-400" : m.kind === "ok" ? "text-green-400" : "text-neutral-500"}`;

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#0d0d0d] px-5 py-12">
      {/* 背景层：对角渐变 + 顶部深色渐变（方案 §2，常量取自参考实现） */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0"
        style={{ background: "linear-gradient(149deg, #1b1b1b 0%, #4f4f4f 100%)" }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{ background: "linear-gradient(180deg, #0d0d0d 0%, #0d0d0d 36%, rgba(47,47,47,0) 100%)" }}
      />

      <ParticleOrb anchorRef={cardRef} />

      {/* 噪点纹理 + 底部辉光 */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.02]"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(1000px 620px at 50% 118%, rgba(255,255,255,0.05), transparent 60%)" }}
      />

      <section className="relative z-10 flex w-full justify-center">
        <div
          ref={cardRef}
          className="relative w-full max-w-[720px] rounded-[18px] border border-white/[0.14] p-2 text-left"
          style={{
            background: "linear-gradient(180deg, rgba(26,26,30,0.92) 0%, rgba(37,37,37,0.94) 100%)",
            backdropFilter: "blur(18px)",
            WebkitBackdropFilter: "blur(18px)",
            boxShadow:
              "0 60px 140px -45px rgba(0,0,0,0.98), 0 24px 60px -30px rgba(0,0,0,0.75), inset 0 1px 0 rgba(255,255,255,0.08)",
          }}
        >
          {/* 光束带 */}
          <span
            aria-hidden
            className="pointer-events-none absolute left-0 right-0 top-[57%] z-0 h-[46px] -translate-y-1/2"
            style={{
              background:
                "linear-gradient(90deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.20) 22%, rgba(255,255,255,0.30) 50%, rgba(255,255,255,0.20) 78%, rgba(255,255,255,0.08) 100%)",
              filter: "blur(14px)",
            }}
          />

          <div
            className="relative z-[1] rounded-xl border border-white/[0.06] bg-[#282828] px-[22px] pb-[18px] pt-5"
            style={{ boxShadow: "inset 0 1px 0 rgba(255,255,255,0.09)" }}
          >
            <div className="mb-4 flex items-center gap-2.5">
              <span className="grid h-[26px] w-[26px] flex-none place-items-center rounded-[7px] border border-white/[0.14]" style={{ background: "linear-gradient(180deg, #262626, #0a0a0a)" }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                  <path d="M2 12h3l2-7 3 14 3-11 2 5h7" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <span className="text-sm font-bold tracking-wider">GraphRAG</span>
              <span className="ml-auto inline-flex items-center gap-2 text-[11px] tracking-[1.2px] text-neutral-500">
                <span className="h-1.5 w-1.5 rounded-full bg-green-400 shadow-[0_0_8px_#4ade80]" />
                V0.1 ONLINE
              </span>
            </div>

            <div className="mb-4 flex gap-2" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={tab === "login"}
                onClick={() => setTab("login")}
                className={`${TAB_BASE} ${tab === "login" ? TAB_ACTIVE : TAB_IDLE}`}
              >
                登录
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "register"}
                onClick={() => setTab("register")}
                className={`${TAB_BASE} ${tab === "register" ? TAB_ACTIVE : TAB_IDLE}`}
              >
                注册
              </button>
            </div>

            {/* 登录 */}
            <form id="login-form" className={tab === "login" ? "block" : "hidden"} onSubmit={onLoginSubmit} noValidate>
              <div className="mb-3">
                <label htmlFor="login-username" className={FIELD_LABEL}>
                  用户名
                </label>
                <input
                  id="login-username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  placeholder="输入你的用户名"
                  className={FIELD_INPUT}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>
              <div className="mb-3">
                <label htmlFor="login-password" className={FIELD_LABEL}>
                  密码
                </label>
                <input
                  id="login-password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  placeholder="输入你的密码"
                  className={FIELD_INPUT}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <p className={msgClass(loginMsg)}>{loginMsg.text}</p>
            </form>

            {/* 注册（UI 占位，接口后续接入，方案 §5） */}
            <form id="register-form" className={tab === "register" ? "block" : "hidden"} onSubmit={onRegisterSubmit} noValidate>
              <div className="mb-3">
                <label htmlFor="reg-username" className={FIELD_LABEL}>
                  用户名
                </label>
                <input
                  id="reg-username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  placeholder="设置你的用户名"
                  className={FIELD_INPUT}
                  value={regUsername}
                  onChange={(e) => setRegUsername(e.target.value)}
                />
              </div>
              <div className="mb-3">
                <label htmlFor="reg-password" className={FIELD_LABEL}>
                  密码
                </label>
                <input
                  id="reg-password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  placeholder="设置密码（至少 8 位）"
                  className={FIELD_INPUT}
                  value={regPassword}
                  onChange={(e) => setRegPassword(e.target.value)}
                />
              </div>
              <div className="mb-3">
                <label htmlFor="reg-confirm" className={FIELD_LABEL}>
                  确认密码
                </label>
                <input
                  id="reg-confirm"
                  name="confirm"
                  type="password"
                  autoComplete="new-password"
                  placeholder="再次输入密码"
                  className={FIELD_INPUT}
                  value={regConfirm}
                  onChange={(e) => setRegConfirm(e.target.value)}
                />
              </div>
              <p className={msgClass(regMsg)}>{regMsg.text}</p>
            </form>
          </div>

          <div className="relative z-[1] flex items-center justify-between px-3 pb-1.5 pt-3">
            <span className="inline-flex items-center gap-2.5 text-[13px] font-medium text-neutral-400">
              <span className="h-[7px] w-[7px] rounded-full bg-green-400 shadow-[0_0_8px_#4ade80]" />
              GraphRAG Console
            </span>
            <button
              type="submit"
              form={tab === "login" ? "login-form" : "register-form"}
              disabled={busy}
              className="rounded-[10px] bg-white px-[26px] py-2 text-[13px] font-bold tracking-[0.08em] text-black transition-shadow disabled:opacity-55 disabled:shadow-none"
              style={{ boxShadow: "0 0 18px rgba(255,255,255,0.25), 0 0 4px rgba(255,255,255,0.35)" }}
              onMouseEnter={(e) => {
                if (!busy) e.currentTarget.style.boxShadow = "0 0 30px rgba(255,255,255,0.45), 0 0 8px rgba(255,255,255,0.5)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.boxShadow = "0 0 18px rgba(255,255,255,0.25), 0 0 4px rgba(255,255,255,0.35)";
              }}
            >
              {busy ? "登录中…" : tab === "login" ? "登 录" : "注 册"}
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
