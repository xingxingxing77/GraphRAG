"""
Prompt Bar 占位端点（14 1:1 复刻 · 前端 @源 / /命令 / +附件 / Connect 占位）。

前端已按首条参考代码 1:1 落地（glimm 彩虹扫光 / 品牌 SVG / AUTO_STEPS 自走），
后端缺真实实现时先返回写死表，不阻塞 UI。后续接：
- SOURCES → ingestion/pipeline_config.yaml pipeline.ingestion.sources
- COMMANDS → planner plan templates / slash command registry
- attach → 对象存储或本地 uploads
- integrations/connect → OAuth 集成（Figma/Gmail）
- skills → app/skills/registry.py （仿 OpenHarness loader.py/registry.py/types.py）

路径前缀由 main.py 挂为 /api/v1/prompt-bar
"""

# --- 标准库 ---
import uuid
from pathlib import Path
from typing import Any

# --- 第三方库 ---
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi import HTTPException
from pydantic import BaseModel

from app.api.security import get_current_user
from app.skills.registry import create_skill_dir, get_skill_registry, get_skills_root

router = APIRouter()

# 附件落盘根（与 skills 同级 data/uploads）
_ATTACH_ROOT = Path(__file__).resolve().parents[2] / "data" / "uploads" / "prompt-bar"


class PromptSource(BaseModel):
    """单条 @ 数据源（前端 SOURCES 1:1）。"""

    key: str
    name: str
    desc: str
    glyph: str | None = None
    brand: str | None = None
    attach: bool | None = None
    connect: bool | None = None


class PromptCommand(BaseModel):
    """单条 / 命令（前端 COMMANDS 1:1）。"""

    key: str
    name: str
    desc: str


# 写死表与前端 src/components/bui/prompt-bar.tsx 保持 1:1
# 2026-08-28 调整：scoop→Add Skill，移除 flavors/slack（需求 2/3），保留 5 行
_SOURCES: list[PromptSource] = [
    PromptSource(key="attach", name="Add photos & files", desc="Upload from your computer", glyph="clip", attach=True),
    PromptSource(key="skill", name="Add Skill", desc="Create or upload a SKILL.md", glyph="layers"),
    PromptSource(key="web", name="Web search", desc="Real-time news and info", glyph="globe"),
    PromptSource(key="figma", name="Figma", desc="Design-to-code workflows", brand="figma"),
    PromptSource(key="gmail", name="Gmail", desc="Read and manage Gmail", brand="gmail", connect=True),
]

_COMMANDS: list[PromptCommand] = [
    PromptCommand(key="compare", name="/compare", desc="Flavor vs. last summer"),
    PromptCommand(key="churn-plan", name="/churn-plan", desc="Draft a churn schedule"),
    PromptCommand(key="restock", name="/restock", desc="Build a reorder list"),
    PromptCommand(key="draft-email", name="/draft-email", desc="Write a supplier email"),
    PromptCommand(key="summarize", name="/summarize", desc="Digest the thread so far"),
]


@router.get("/sources", response_model=list[PromptSource])
async def list_sources() -> list[PromptSource]:
    """列出 @ 数据源写死表（1:1 前端）。

    Returns:
        list[PromptSource]: 7 条，含 attach/connect 标记。
    """
    return _SOURCES


@router.get("/commands", response_model=list[PromptCommand])
async def list_commands() -> list[PromptCommand]:
    """列出 / 命令写死表（1:1 前端）。

    Returns:
        list[PromptCommand]: 5 条。
    """
    return _COMMANDS


class SkillCreateRequest(BaseModel):
    """创建 Skill 请求（JSON 形态，对应 OpenHarness SkillDefinition）。"""

    name: str
    description: str | None = None
    content: str


class SkillCreateResponse(BaseModel):
    """创建 Skill 响应."""

    ok: bool
    name: str | None = None
    path: str | None = None
    error: str | None = None


@router.get("/skills", response_model=list[dict[str, Any]])
async def list_skills() -> list[dict[str, Any]]:
    """列出已安装的 Skills（仿 OpenHarness registry.list_skills）。"""
    reg = get_skill_registry()
    return [
        {"name": s.name, "description": s.description, "path": s.path, "command_name": s.command_name}
        for s in reg.list_skills()
    ]


@router.post("/skills", response_model=SkillCreateResponse)
async def create_skill(
    req: SkillCreateRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> SkillCreateResponse:
    """创建 Skill（落盘 <skills_root>/<name>/SKILL.md 并注册）。

    M10：写端点须持 JWT（与全站其余写端点一致），防匿名批量落盘。

    Args:
        req: name/description/content。
        user: JWT 用户声明。

    Returns:
        SkillCreateResponse
    """
    try:
        skill = create_skill_dir(req.name, req.content, req.description)
        return SkillCreateResponse(ok=True, name=skill.name, path=skill.path)
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/skills/upload")
async def upload_skill_file(
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """上传 SKILL.md 文件创建 Skill（multipart，回退解析文件名作为 name）。

    M10：写端点须持 JWT（同 create_skill）。

    Args:
        file: SKILL.md 文件。
        user: JWT 用户声明。

    Returns:
        dict
    """
    raw = (await file.read()).decode("utf-8", errors="ignore")
    # 优先用文件名前缀作为 default_name
    default_name = (file.filename or "skill").rsplit(".", 1)[0].lower().replace(" ", "-")[:32] or "skill"
    # 若含 frontmatter 则交由 registry 解析
    try:
        # 尝试从 content 的 frontmatter 拿 name
        skill = create_skill_dir(default_name, raw, None)
        return {"ok": True, "name": skill.name, "path": skill.path}
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/attach")
async def attach_files(
    files: list[UploadFile] = File(...),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """接收附件上传（落盘 data/uploads/prompt-bar/<uuid>/ 并回显）。

    M10：写端点须持 JWT，防匿名无限批量写入磁盘。

    Args:
        files: 上传文件列表。
        user: JWT 用户声明。

    Returns:
        dict: 回显文件名与 url。
    """
    _ATTACH_ROOT.mkdir(parents=True, exist_ok=True)
    batch = uuid.uuid4().hex[:8]
    batch_dir = _ATTACH_ROOT / batch
    batch_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for f in files:
        content = await f.read()
        # 文件名消毒：仅保留 basename
        safe_name = Path(f.filename or "upload.bin").name
        dest = batch_dir / safe_name
        dest.write_bytes(content)
        items.append(
            {
                "name": safe_name,
                "size": len(content),
                "content_type": f.content_type,
                "url": f"/data/uploads/prompt-bar/{batch}/{safe_name}",
                "path": str(dest),
            }
        )
    return {"ok": True, "files": items}


@router.post("/integrations/{provider}/connect")
async def connect_integration(provider: str) -> dict[str, Any]:
    """占位：标记外部集成已连接（Figma/Gmail；Slack 已移除）。

    Args:
        provider: 提供方 key（figma/gmail）。

    Returns:
        dict: 占位成功标记；真实实现后续接 OAuth。
    """
    allowed = {"figma", "gmail"}
    if provider not in allowed:
        return {"ok": False, "error": f"unknown provider: {provider}"}
    return {"ok": True, "provider": provider, "connected": True, "note": "占位：前端已显示 Connected，后端待接 OAuth"}
