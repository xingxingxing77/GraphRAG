/**
 * WorkspaceSidebar（06 §8 v1.3）：Chat 左侧工作区侧栏。
 * 结构：产品名头 + 折叠按钮 / 新会话 / 会话搜索 / 时间分组树
 * （今天/7天内/更早，sessionStore.groupSessions 派生）/ 底部导航
 * （图谱、管理台[仅 admin]、设置·主题持久化）。删除会话需二次确认
 * （DELETE 级联记忆，02 §3.4）。BUI 落点：sidebar-nav + search。
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  BarChart3,
  MessageSquare,
  Moon,
  PanelLeft,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Trash2,
} from "lucide-react";

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

/**
 * 相对时间文案（原型"6天"样式）。
 *
 * @param iso - ISO 8601 时间串。
 * @returns 刚刚 / N分钟前 / N小时前 / N天前；无法解析返回空串。
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
 * 渲染工作区侧栏（可折叠为图标窄条）。
 *
 * @param props - 见 WorkspaceSidebarProps。
 * @returns 侧栏元素。
 */
export function WorkspaceSidebar(props: WorkspaceSidebarProps) {
  const { sessions, activeId, onSelect, onNew, onDelete, onSearch } = props;
  const [collapsed, setCollapsed] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isAdmin] = useState(
    () => JSON.parse(sessionStorage.getItem("rag_user") ?? "null")?.role === "admin",
  );
  const grouped = groupSessions(sessions);

  /** 删除前二次确认（级联记忆，02 §3.4）。 */
  function handleDelete(id: string) {
    if (window.confirm("删除该会话及其全部记忆？此操作不可恢复。")) onDelete(id);
  }

  /** 主题切换（class="dark" 持久化，06 §11）。 */
  function toggleTheme() {
    const el = document.documentElement;
    const dark = el.classList.toggle("dark");
    localStorage.setItem("rag_theme", dark ? "dark" : "light");
  }

  if (collapsed) {
    return (
      <aside className="flex h-full w-14 flex-col items-center gap-3 border-r py-3">
        <button
          className="rounded p-1.5 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
          onClick={() => setCollapsed(false)}
          aria-label="展开侧栏"
        >
          <PanelLeft size={16} />
        </button>
        <button
          className="rounded-full bg-neutral-900 p-2 text-white dark:bg-white dark:text-neutral-900"
          onClick={onNew}
          aria-label="新会话"
        >
          <Plus size={14} />
        </button>
        <Link to="/graph" className="rounded p-1.5 text-neutral-500 hover:bg-neutral-100" aria-label="图谱">
          <BarChart3 size={16} />
        </Link>
        {isAdmin ? (
          <Link to="/admin" className="rounded p-1.5 text-neutral-500 hover:bg-neutral-100" aria-label="管理台">
            <ShieldCheck size={16} />
          </Link>
        ) : null}
        <div className="mt-auto">
          <button className="rounded p-1.5 text-neutral-500 hover:bg-neutral-100" onClick={toggleTheme} aria-label="切换主题">
            <Moon size={16} />
          </button>
        </div>
      </aside>
    );
  }

  return (
    <aside className="flex h-full w-72 flex-col border-r bg-neutral-50/60 dark:bg-neutral-900/40">
      {/* 头部：产品名 + 折叠 */}
      <div className="flex items-center justify-between px-4 pt-4">
        <span className="text-[15px] font-semibold tracking-tight">GraphRAG</span>
        <button
          className="rounded p-1.5 text-neutral-500 hover:bg-neutral-200/60 dark:hover:bg-neutral-800"
          onClick={() => setCollapsed(true)}
          aria-label="折叠侧栏"
        >
          <PanelLeft size={15} />
        </button>
      </div>

      {/* 新会话 */}
      <div className="px-3 pt-3">
        <button
          className="w-full rounded-xl border border-neutral-200 bg-white py-2.5 text-sm font-medium shadow-sm transition-colors hover:border-neutral-300 hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-800 dark:hover:bg-neutral-700"
          onClick={onNew}
        >
          <span className="inline-flex items-center gap-1.5">
            <Plus size={14} /> 新会话
          </span>
        </button>
      </div>

      {/* 会话区头：标题 + 搜索开关 */}
      <div className="mt-5 flex items-center justify-between px-4">
        <span className="text-xs font-medium text-neutral-500">会话</span>
        <button
          className="rounded p-1 text-neutral-500 hover:bg-neutral-200/60 dark:hover:bg-neutral-800"
          onClick={() => {
            setSearchOpen((v) => !v);
            if (searchOpen) {
              setQuery("");
              onSearch("");
            }
          }}
          aria-label="搜索会话"
        >
          <Search size={13} />
        </button>
      </div>
      {searchOpen ? (
        <div className="px-3 pt-2">
          <input
            autoFocus
            className="w-full rounded-lg border border-neutral-200 bg-white px-2.5 py-1.5 text-xs outline-none focus:border-neutral-400 dark:border-neutral-700 dark:bg-neutral-800"
            placeholder="按标题过滤…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              onSearch(e.target.value);
            }}
          />
        </div>
      ) : null}

      {/* 时间分组树 */}
      <nav className="mt-2 flex-1 overflow-y-auto px-2 pb-2">
        {sessions.length === 0 ? (
          <p className="px-2 py-6 text-xs text-neutral-400">
            暂无会话（后端就绪后自动加载）
          </p>
        ) : null}
        {SESSION_GROUP_ORDER.map((key) => {
          const items = grouped[key];
          if (items.length === 0) return null;
          return (
            <div key={key} className="mb-1">
              <p className="px-2 pb-1 pt-2 text-[11px] font-medium text-neutral-400">
                {SESSION_GROUP_LABELS[key]}
              </p>
              {items.map((s) => (
                <div
                  key={s.session_id}
                  className={`group flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm ${
                    activeId === s.session_id
                      ? "bg-neutral-200/70 font-medium dark:bg-neutral-700/70"
                      : "hover:bg-neutral-200/40 dark:hover:bg-neutral-800/60"
                  }`}
                  onClick={() => onSelect(s.session_id)}
                >
                  <MessageSquare size={13} className="shrink-0 text-neutral-400" />
                  <span className="flex-1 truncate">{s.title || "未命名会话"}</span>
                  <span className="shrink-0 text-[11px] text-neutral-400 group-hover:hidden">
                    {relTime(s.updated_at)}
                  </span>
                  <button
                    className="hidden shrink-0 rounded p-0.5 text-neutral-400 hover:text-red-500 group-hover:block"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(s.session_id);
                    }}
                    aria-label="删除会话"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
          );
        })}
      </nav>

      {/* 底部导航 + 设置 */}
      <div className="border-t px-2 py-2 text-sm">
        <Link
          to="/graph"
          className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-neutral-600 hover:bg-neutral-200/50 dark:text-neutral-300 dark:hover:bg-neutral-800"
        >
          <BarChart3 size={15} /> 图谱
        </Link>
        {isAdmin ? (
          <Link
            to="/admin"
            className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-neutral-600 hover:bg-neutral-200/50 dark:text-neutral-300 dark:hover:bg-neutral-800"
          >
            <ShieldCheck size={15} /> 管理台
          </Link>
        ) : null}
        <div className="relative">
          <button
            className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-neutral-600 hover:bg-neutral-200/50 dark:text-neutral-300 dark:hover:bg-neutral-800"
            onClick={() => setSettingsOpen((v) => !v)}
          >
            <Settings size={15} /> 设置
          </button>
          {settingsOpen ? (
            <div className="absolute bottom-full left-2 mb-2 w-52 rounded-xl border border-neutral-200 bg-white p-3 text-xs shadow-lg dark:border-neutral-700 dark:bg-neutral-800">
              <button
                className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-700"
                onClick={toggleTheme}
              >
                <Moon size={13} /> 切换明暗主题
              </button>
              <p className="px-2 pt-1.5 text-[11px] text-neutral-400">
                偏好设置随单元 10.5 扩展
              </p>
            </div>
          ) : null}
        </div>
      </div>
    </aside>
  );
}
