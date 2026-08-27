/**
 * Prompt Bar 占位接口封装（14 1:1 复刻，后端见 app/api/endpoints/prompt_bar.py）。
 * 前端已 1:1 展示 SOURCES/COMMANDS/attach/connect，后端缺失时静默降级为本地写死表。
 */
import { http } from "./http";

export interface PromptSource {
  key: string;
  name: string;
  desc: string;
  glyph?: string | null;
  brand?: string | null;
  attach?: boolean | null;
  connect?: boolean | null;
}

export interface PromptCommand {
  key: string;
  name: string;
  desc: string;
}

/** 拉取 @ 数据源（失败回退 null，由调用方用前端写死表）。 */
export function listPromptSources(): Promise<PromptSource[]> {
  return http.get<PromptSource[]>("/prompt-bar/sources").then((r) => r.data);
}

/** 拉取 / 命令（失败回退 null）。 */
export function listPromptCommands(): Promise<PromptCommand[]> {
  return http.get<PromptCommand[]>("/prompt-bar/commands").then((r) => r.data);
}

/** 上传附件（落盘 data/uploads/prompt-bar/<batch>/）。 */
export function attachPromptFiles(files: File[]): Promise<{ ok: boolean; files: { name: string; size: number; url?: string }[] }> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  return http.post("/prompt-bar/attach", form).then((r) => r.data);
}

/** 标记外部集成已连接（figma/gmail；slack 已移除）。 */
export function connectPromptIntegration(provider: string): Promise<{ ok: boolean; connected?: boolean }> {
  return http.post(`/prompt-bar/integrations/${provider}/connect`).then((r) => r.data);
}

export interface PromptSkill {
  name: string;
  description: string;
  path?: string | null;
  command_name?: string | null;
}

/** 列出已安装 Skills。 */
export function listPromptSkills(): Promise<PromptSkill[]> {
  return http.get<PromptSkill[]>("/prompt-bar/skills").then((r) => r.data);
}

/** 创建 Skill（JSON）。 */
export function createPromptSkill(payload: { name: string; description?: string; content: string }): Promise<{ ok: boolean; name?: string; path?: string }> {
  return http.post("/prompt-bar/skills", payload).then((r) => r.data);
}

/** 上传 SKILL.md 文件创建 Skill。 */
export function uploadPromptSkillFile(file: File): Promise<{ ok: boolean; name?: string; path?: string }> {
  const form = new FormData();
  form.append("file", file);
  return http.post("/prompt-bar/skills/upload", form).then((r) => r.data);
}
