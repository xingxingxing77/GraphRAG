/**
 * WorkspaceSidebar（06 §8 v1.3  ·  10.7 1:1 复刻 sidebar-nav 设计壳）
 * 结构：工作区切换器（portal 下拉）/ 主导航（New chat + 图谱/管理台）/
 * 可搜索会话历史（right→left 180ms 展开 + 分组树）/ 折叠联动（52/224）。
 * 排除：原设计 Invite users / Upgrade 底栏（用户定案）。
 * BUI 落点：sidebar-nav + search + GlideMenu 基元。
 */
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import {
  BarChart3,
  Check,
  ChevronDown,
  Home,
  LogOut,
  MessageSquare,
  Moon,
  PanelLeft,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  SquarePen,
  Trash2,
  X,
} from "lucide-react";

import GlideMenu from "@/components/bui/primitives/glide-menu";
import {
  groupSessions,
  SESSION_GROUP_LABELS,
  SESSION_GROUP_ORDER,
} from "@/stores/sessionStore";
import type { SessionSummary } from "@/types";

/** 侧栏 Props（06 §8 约定）。 */
export interface WorkspaceSidebarProps {
  sessions: SessionSummary[];
  activeId: string | null;
  onSelect(sessionId: string): void;
  onNew(): void;
  onDelete(sessionId: string): void;
  onSearch(query: string): void;
}

const WORKSPACE = { key: "graphrag", name: "GraphRAG", monogram: "G" };

const SIDEBAR_MOTION = {
  expandedWidth: 224,
  collapsedWidth: 52,
  duration: 280,
  copyDuration: 180,
  copyOffset: 8,
  easing: "cubic-bezier(0.16, 1, 0.3, 1)",
};

/* ─────────────────────────────────────────────────────────
 * CHAT SEARCH STORYBOARD（1:1 复刻 sidebar-nav）
 *   0ms   search is triggered; Chats label begins fading
 *   0ms   field grows right → left from the search control
 * 180ms   field fills the row; cursor is focused and ready
 * ───────────────────────────────────────────────────────── */
const CHAT_SEARCH_MOTION = {
  duration: 180,
  closedWidth: 28,
  easing: "cubic-bezier(0.16, 1, 0.3, 1)",
};

function GlideGroup({ children }: { children: ReactNode }) {
  return (
    <GlideMenu
      rowSelector="[data-row]"
      highlightClassName="sidebar-glide-highlight rounded-[7px] bg-hover-2"
      className="group/glide flex flex-col gap-px"
    >
      {children}
    </GlideMenu>
  );
}

function RailButton({
  icon,
  label,
  active = false,
  count,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  active?: boolean;
  count?: string;
  onClick?: () => void;
}) {
  return (
    <button
      data-row
      type="button"
      onClick={onClick}
      className={`sidebar-row relative z-10 mx-2 flex h-8 items-center rounded-[8px] px-2 text-left transition-[width,background-color,color,transform] duration-150 active:scale-[0.98] ${active ? "bg-hover-2 group-hover/glide:bg-transparent" : ""}`}
    >
      <span className={`flex size-5 shrink-0 items-center justify-center ${active ? "text-ink" : "text-ink-2"}`}>{icon}</span>
      <span className={`sidebar-copy ml-1.5 min-w-0 flex-1 truncate text-[14px] font-medium ${active ? "text-ink" : "text-ink-2"}`}>{label}</span>
      {count && <span className="sidebar-copy mr-2 shrink-0 text-[12px] font-medium tabular-nums text-ink-3">{count}</span>}
    </button>
  );
}

function LinkRow({
  to,
  icon,
  label,
}: {
  to: string;
  icon: ReactNode;
  label: string;
}) {
  return (
    <Link
      data-row
      to={to}
      className="sidebar-row relative z-10 mx-2 flex h-8 items-center rounded-[8px] px-2 text-left transition-[width,background-color,color,transform] duration-150 active:scale-[0.98]"
    >
      <span className="flex size-5 shrink-0 items-center justify-center text-ink-2">{icon}</span>
      <span className="sidebar-copy ml-1.5 min-w-0 flex-1 truncate text-[14px] font-medium text-ink-2">{label}</span>
    </Link>
  );
}

function WorkspaceMenu({
  position,
  onClose,
}: {
  position: { top: number; left: number };
  onClose: () => void;
}) {
  return createPortal(
    <div
      data-workspace-menu
      className="fixed z-50 w-64 rounded-[14px] bg-surface p-1.5 shadow-overlay"
      style={{
        top: position.top,
        left: position.left,
        animation: "pop-in 180ms cubic-bezier(0.23,1,0.32,1) both",
        transformOrigin: "top left",
      }}
    >
      <GlideMenu className="flex flex-col gap-px" highlightClassName="inset-x-0 rounded-[8px] bg-hover-2">
        <button
          data-menu-row
          type="button"
          onClick={onClose}
          className="relative z-10 flex h-10 w-full items-center gap-1.5 rounded-[8px] px-2 text-left"
        >
          <span className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-ink text-[11px] font-semibold text-surface">
            {WORKSPACE.monogram}
          </span>
          <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-ink">{WORKSPACE.name}</span>
          <span className="shrink-0 text-ink">
            <Check size={18} />
          </span>
        </button>
        <div className="my-1 h-px bg-line" />
        {[
          { label: "New workspace", icon: <Plus size={16} /> },
          { label: "Workspace settings", icon: <Settings size={16} /> },
        ].map((item) => (
          <button
            key={item.label}
            data-menu-row
            type="button"
            onClick={onClose}
            className="relative z-10 flex h-9 w-full items-center gap-1.5 rounded-[8px] px-2 text-left"
          >
            <span className="flex size-5 shrink-0 items-center justify-center text-ink-2">{item.icon}</span>
            <span className="min-w-0 flex-1 truncate text-[13.5px] text-ink">{item.label}</span>
          </button>
        ))}
        <div className="my-1 h-px bg-line" />
        <button
          data-menu-row
          type="button"
          onClick={onClose}
          className="relative z-10 flex h-9 w-full items-center gap-1.5 rounded-[8px] px-2 text-left"
        >
          <span className="flex size-5 shrink-0 items-center justify-center text-ink-2">
            <LogOut size={16} />
          </span>
          <span className="min-w-0 flex-1 truncate text-[13.5px] text-ink">Sign out</span>
        </button>
      </GlideMenu>
    </div>,
    document.body,
  );
}

/**
 * 相对时间文案（原型"6天"样式）。
 */
function relTime(iso: string | undefined): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const diff = Date.now() - t;
  const min = Math.floor(diff / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min}分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}小时前`;
  return `${Math.floor(hr / 24)}天前`;
}

/**
 * 渲染工作区侧栏（1:1 复刻 sidebar-nav 壳 + 业务会话树）。
 */
export function WorkspaceSidebar(props: WorkspaceSidebarProps) {
  const { sessions, activeId, onSelect, onNew, onDelete, onSearch } = props;
  const [collapsed, setCollapsed] = useState(false);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [workspacePosition, setWorkspacePosition] = useState({ top: 0, left: 0 });
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isAdmin] = useState(() => JSON.parse(sessionStorage.getItem("rag_user") ?? "null")?.role === "admin");
  const workspaceButtonRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const filtered = (() => {
    const q = query.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => (s.title ?? "").toLowerCase().includes(q));
  })();
  const grouped = groupSessions(filtered);

  function handleDelete(id: string) {
    if (window.confirm("删除该会话及其全部记忆？此操作不可恢复。")) onDelete(id);
  }

  function toggleTheme() {
    const el = document.documentElement;
    const dark = el.classList.toggle("dark");
    localStorage.setItem("rag_theme", dark ? "dark" : "light");
  }

  useEffect(() => {
    if (!workspaceOpen) return;
    const close = (event: PointerEvent) => {
      const target = event.target as Element;
      if (!target.closest("[data-workspace-trigger]") && !target.closest("[data-workspace-menu]")) {
        setWorkspaceOpen(false);
      }
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [workspaceOpen]);

  useEffect(() => {
    if (searchOpen) searchRef.current?.focus();
  }, [searchOpen]);

  useEffect(() => {
    if (!settingsOpen) return;
    const close = (event: PointerEvent) => {
      const target = event.target as Element;
      if (!target.closest("[data-settings-trigger]") && !target.closest("[data-settings-menu]")) {
        setSettingsOpen(false);
      }
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [settingsOpen]);

  const collapse = () => {
    setCollapsed(true);
    setWorkspaceOpen(false);
    setSearchOpen(false);
    setQuery("");
    onSearch("");
  };

  return (
    <aside
      data-sidebar-collapsed={collapsed}
      aria-label="Workspace navigation"
      className="relative flex shrink-0 overflow-hidden border-r bg-surface transition-[width] dark:border-neutral-800"
      style={
        {
          width: collapsed ? SIDEBAR_MOTION.collapsedWidth : SIDEBAR_MOTION.expandedWidth,
          transitionDuration: `${SIDEBAR_MOTION.duration}ms`,
          transitionTimingFunction: SIDEBAR_MOTION.easing,
          "--sidebar-copy-duration": `${SIDEBAR_MOTION.copyDuration}ms`,
          "--sidebar-copy-offset": `${SIDEBAR_MOTION.copyOffset}px`,
          "--sidebar-easing": SIDEBAR_MOTION.easing,
        } as CSSProperties
      }
    >
      <div className="flex min-h-0 w-[224px] shrink-0 flex-col">
        {/* 顶部：工作区切换器 + 折叠 */}
        <div className="relative mb-2.5 h-10 shrink-0">
          <button
            ref={workspaceButtonRef}
            data-workspace-trigger
            type="button"
            aria-expanded={workspaceOpen}
            aria-hidden={collapsed}
            tabIndex={collapsed ? -1 : 0}
            onClick={() => {
              if (!workspaceOpen && workspaceButtonRef.current) {
                const rect = workspaceButtonRef.current.getBoundingClientRect();
                setWorkspacePosition({ top: rect.bottom + 6, left: rect.left });
              }
              setWorkspaceOpen((open) => !open);
            }}
            className="sidebar-workspace-control absolute left-2 top-1 flex h-8 w-[164px] items-center rounded-[8px] px-2 text-left transition-[background-color,transform] duration-100 hover:bg-hover-2 active:scale-[0.99]"
          >
            <span className="sidebar-logo flex size-5 shrink-0 items-center justify-center text-[13px] font-bold text-ink">G</span>
            <span className="sidebar-copy ml-1.5 min-w-0 flex-1 truncate text-[14px] font-medium text-ink-2">{WORKSPACE.name}</span>
            <span className="sidebar-copy ml-1 flex shrink-0 text-ink-3">
              <ChevronDown size={16} />
            </span>
          </button>

          {workspaceOpen && <WorkspaceMenu position={workspacePosition} onClose={() => setWorkspaceOpen(false)} />}

          <button
            type="button"
            aria-label="折叠侧栏"
            aria-hidden={collapsed}
            tabIndex={collapsed ? -1 : 0}
            onClick={collapse}
            className="sidebar-collapse-control absolute right-2 top-1 flex size-8 items-center justify-center rounded-[8px] text-ink-3 transition-[opacity,background-color,color] duration-150 hover:bg-hover-2 hover:text-ink"
          >
            <PanelLeft size={18} />
          </button>
          <button
            type="button"
            aria-label="展开侧栏"
            aria-hidden={!collapsed}
            tabIndex={collapsed ? 0 : -1}
            onClick={() => setCollapsed(false)}
            className="sidebar-expand-control absolute left-2 top-0.5 flex size-9 items-center justify-center rounded-[8px] text-ink-3 transition-[opacity,background-color,color] duration-150 hover:bg-hover-2 hover:text-ink"
          >
            <PanelLeft size={18} className="rotate-180" />
          </button>
        </div>

        {/* 主导航：新会话 + 图谱/管理台（1:1 的 RailButton/LinkRow + Glide 高亮） */}
        <GlideGroup>
          <RailButton
            icon={<SquarePen size={18} />}
            label="新会话"
            onClick={() => {
              setQuery("");
              onSearch("");
              onNew();
            }}
          />
          <RailButton icon={<Home size={18} />} label="Home" active={false} onClick={onNew} />
          <LinkRow to="/graph" icon={<BarChart3 size={18} />} label="图谱" />
          {isAdmin ? <LinkRow to="/admin" icon={<ShieldCheck size={18} />} label="管理台" /> : null}
        </GlideGroup>

        {/* 会话区：可搜索标题 + 时间分组树（Glide 高亮、active 态、删除） */}
        <div className="mt-3 min-h-0 flex-1 overflow-y-auto">
          <div className="sidebar-copy relative mx-2 mb-1 h-8">
            <div
              aria-hidden={searchOpen}
              className={`absolute inset-0 flex items-center gap-1.5 px-2 text-[12.5px] font-medium text-ink-3 transition-[opacity,transform] ${searchOpen ? "pointer-events-none -translate-x-1 opacity-0" : "translate-x-0 opacity-100"}`}
              style={{ transitionDuration: `${CHAT_SEARCH_MOTION.duration}ms`, transitionTimingFunction: CHAT_SEARCH_MOTION.easing }}
            >
              <ChevronDown size={16} />
              <span>会话</span>
            </div>

            <button
              type="button"
              aria-label="搜索会话"
              aria-expanded={searchOpen}
              onClick={() => setSearchOpen(true)}
              className={`absolute right-0 top-0 z-10 flex size-8 items-center justify-center rounded-[8px] text-ink-3 transition-[opacity,background-color,color,transform] hover:bg-hover-2 hover:text-ink active:scale-[0.96] ${searchOpen ? "pointer-events-none opacity-0" : "opacity-100"}`}
              style={{ transitionDuration: `${CHAT_SEARCH_MOTION.duration}ms` }}
            >
              <Search size={16} />
            </button>

            <div
              className={`absolute right-0 top-0 z-20 flex h-8 items-center overflow-hidden rounded-[8px] bg-field text-ink-3 shadow-hairline transition-[width,opacity] focus-within:text-ink-2 ${searchOpen ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0"}`}
              style={{
                width: searchOpen ? "100%" : CHAT_SEARCH_MOTION.closedWidth,
                transitionDuration: `${CHAT_SEARCH_MOTION.duration}ms`,
                transitionTimingFunction: CHAT_SEARCH_MOTION.easing,
              }}
            >
              <span className="ml-2 flex shrink-0 items-center justify-center">
                <Search size={15} />
              </span>
              <input
                ref={searchRef}
                value={query}
                onChange={(event) => {
                  const v = event.target.value;
                  setQuery(v);
                  onSearch(v);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    setSearchOpen(false);
                    setQuery("");
                    onSearch("");
                  }
                }}
                placeholder="搜索会话"
                aria-label="搜索会话"
                className="ml-1.5 min-w-0 flex-1 bg-transparent text-[13px] font-medium text-ink outline-none placeholder:text-ink-3"
              />
              <button
                type="button"
                aria-label="关闭搜索"
                onClick={() => {
                  setSearchOpen(false);
                  setQuery("");
                  onSearch("");
                }}
                className="flex size-8 shrink-0 items-center justify-center rounded-[8px] text-ink-3 transition-[background-color,color,transform] duration-150 hover:bg-hover-2 hover:text-ink active:scale-[0.96]"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          {sessions.length === 0 ? (
            <p className="sidebar-copy px-4 py-6 text-xs text-ink-3">暂无会话（后端就绪后自动加载）</p>
          ) : null}

          {SESSION_GROUP_ORDER.map((key) => {
            const items = grouped[key];
            if (items.length === 0) return null;
            return (
              <div key={key} className="mb-1">
                <p className="sidebar-copy px-4 pb-1 pt-2 text-[11px] font-medium text-ink-3">{SESSION_GROUP_LABELS[key]}</p>
                <GlideGroup>
                  {items.map((s) => {
                    const active = s.session_id === activeId;
                    return (
                      <button
                        key={s.session_id}
                        data-row
                        type="button"
                        title={s.title || "未命名会话"}
                        onClick={() => onSelect(s.session_id)}
                        className={`sidebar-row group/row relative z-10 mx-2 flex h-8 items-center rounded-[8px] px-2 text-left transition-[width,background-color,color,transform] duration-150 active:scale-[0.98] ${active ? "bg-hover-2 group-hover/glide:bg-transparent" : ""}`}
                      >
                        <MessageSquare size={14} className={`hidden size-4 shrink-0 sm:flex ${active ? "text-ink" : "text-ink-3"}`} />
                        <span
                          className={`sidebar-copy ml-1.5 min-w-0 flex-1 truncate text-[14px] font-medium ${active ? "text-ink" : "text-ink-2"}`}
                        >
                          {s.title || "未命名会话"}
                        </span>
                        <span className="sidebar-copy ml-1 hidden shrink-0 text-[11px] tabular-nums text-ink-3 group-hover/row:hidden sm:block">
                          {relTime(s.updated_at)}
                        </span>
                        <span
                          role="button"
                          tabIndex={0}
                          aria-label="删除会话"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(s.session_id);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              e.stopPropagation();
                              handleDelete(s.session_id);
                            }
                          }}
                          className="sidebar-copy hidden shrink-0 rounded p-0.5 text-ink-3 hover:text-red-500 group-hover/row:flex"
                        >
                          <Trash2 size={13} />
                        </span>
                      </button>
                    );
                  })}
                </GlideGroup>
              </div>
            );
          })}
          {query && filtered.length === 0 && sessions.length > 0 ? (
            <div className="sidebar-copy mx-2 px-2 py-2 text-[12.5px] text-ink-3">无匹配会话</div>
          ) : null}
        </div>

        {/* 底部：设置（替代原 Upgrade 底栏，占同等 208 宽 + border-t 视觉） */}
        <div className="sidebar-copy mx-2 mt-3 w-[208px] border-t border-line pt-3">
          <div className="relative">
            <button
              data-settings-trigger
              type="button"
              onClick={() => setSettingsOpen((v) => !v)}
              className="flex h-8 w-full items-center gap-1.5 rounded-[8px] px-2 text-left text-[14px] font-medium text-ink-2 transition-[background-color,color] duration-150 hover:bg-hover-2 hover:text-ink"
            >
              <span className="flex size-5 shrink-0 items-center justify-center text-ink-2">
                <Settings size={18} />
              </span>
              <span className="min-w-0 flex-1 truncate">设置</span>
            </button>
            {settingsOpen ? (
              <div
                data-settings-menu
                className="absolute bottom-full left-0 mb-2 w-52 rounded-[14px] border border-line bg-surface p-1.5 shadow-overlay"
                style={{ animation: "pop-in 180ms cubic-bezier(0.23,1,0.32,1) both", transformOrigin: "bottom left" }}
              >
                <button
                  type="button"
                  onClick={toggleTheme}
                  className="flex h-9 w-full items-center gap-1.5 rounded-[8px] px-2 text-left text-[13.5px] text-ink transition-colors hover:bg-hover-2"
                >
                  <span className="flex size-5 shrink-0 items-center justify-center text-ink-2">
                    <Moon size={16} />
                  </span>
                  <span className="min-w-0 flex-1 truncate">切换明暗主题</span>
                </button>
                <p className="px-2 pt-1.5 text-[11px] text-ink-3">偏好设置随单元 10.5 扩展</p>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </aside>
  );
}
