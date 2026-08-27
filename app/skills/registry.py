"""Lightweight skill registry — port of E:\\OpenHarness\\src\\openharness\\skills."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

# 根目录：data/skills （与 prompt-bar 附件 data/uploads 同级）
_SKILLS_ROOT = Path(__file__).resolve().parents[2] / "data" / "skills"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")


@dataclass(frozen=True)
class SkillDefinition:
    """A loaded skill (subset of openharness.skills.types.SkillDefinition)."""

    name: str
    description: str
    content: str
    source: str = "user"
    path: str | None = None
    base_dir: str | None = None
    command_name: str | None = None
    display_name: str | None = None


class SkillRegistry:
    """In-memory registry keyed by name/command_name."""

    def __init__(self) -> None:
        self._by_name: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        for key in (skill.name, skill.command_name, skill.display_name):
            if key:
                self._by_name[key] = skill

    def get(self, name: str) -> SkillDefinition | None:
        return self._by_name.get(name)

    def list_skills(self) -> list[SkillDefinition]:
        uniq: dict[str, SkillDefinition] = {}
        for s in self._by_name.values():
            uniq[s.name] = s
        return sorted(uniq.values(), key=lambda s: s.name)

    def clear(self) -> None:
        self._by_name.clear()


# 单例（进程内）
_registry: SkillRegistry | None = None


def get_skills_root() -> Path:
    """Return skills root, ensuring it exists."""
    _SKILLS_ROOT.mkdir(parents=True, exist_ok=True)
    return _SKILLS_ROOT


def _parse_skill_metadata(default_name: str, content: str) -> tuple[str, str]:
    """Parse name/description from SKILL.md frontmatter or first heading/paragraph."""
    name = default_name
    description = ""
    frontmatter: dict = {}
    if content.startswith("---\n"):
        end = content.find("\n---\n", 4)
        if end != -1:
            try:
                data = yaml.safe_load(content[4:end])
                if isinstance(data, dict):
                    frontmatter = data
                    v = data.get("name")
                    if isinstance(v, str) and v.strip():
                        name = v.strip()
                    v = data.get("description")
                    if isinstance(v, str) and v.strip():
                        description = v.strip()
            except yaml.YAMLError:
                pass
    if not description:
        for line in content.splitlines():
            s = line.strip()
            if s.startswith("# "):
                if name == default_name:
                    name = s[2:].strip() or default_name
                continue
            if s and not s.startswith("---") and not s.startswith("#"):
                description = s[:200]
                break
    if not description:
        description = f"Skill: {name}"
    return name, description


def _validate_name(name: str) -> str:
    n = name.strip().lower()
    if not _NAME_RE.match(n):
        raise ValueError("name 需 2-32 位小写字母/数字/中划线，且以字母数字开头")
    return n


def load_skills_from_root(root: Path | None = None) -> list[SkillDefinition]:
    """Scan <root>/*/SKILL.md and return definitions."""
    r = Path(root) if root else get_skills_root()
    if not r.is_dir():
        return []
    out: list[SkillDefinition] = []
    for child in sorted(r.iterdir()):
        if not child.is_dir():
            continue
        p = child / "SKILL.md"
        if not p.exists():
            continue
        content = p.read_text(encoding="utf-8")
        default_name = child.name
        name, description = _parse_skill_metadata(default_name, content)
        try:
            name = _validate_name(name)
        except ValueError:
            name = _validate_name(default_name)
        out.append(
            SkillDefinition(
                name=name,
                description=description,
                content=content,
                source="user",
                path=str(p),
                base_dir=str(child),
                command_name=child.name,
                display_name=name if name != child.name else None,
            )
        )
    return out


def get_skill_registry(*, refresh: bool = False) -> SkillRegistry:
    """Return singleton registry, optionally re-scanning disk."""
    global _registry
    if _registry is None or refresh:
        reg = SkillRegistry()
        for s in load_skills_from_root():
            reg.register(s)
        _registry = reg
    return _registry


def create_skill_dir(name: str, content: str, description: str | None = None) -> SkillDefinition:
    """Create <skills_root>/<name>/SKILL.md with given content.

    If frontmatter missing, prepend one with name/description.
    """
    name = _validate_name(name)
    root = get_skills_root()
    skill_dir = root / name
    if skill_dir.exists():
        raise FileExistsError(f"skill 已存在: {name}")
    # 若 content 未以 --- 开头，补 frontmatter
    if not content.lstrip().startswith("---"):
        fm_desc = (description or content.splitlines()[0][:120] if content else f"Skill: {name}")
        content = f"---\nname: {name}\ndescription: {fm_desc}\n---\n\n{content}"
    skill_dir.mkdir(parents=True, exist_ok=False)
    p = skill_dir / "SKILL.md"
    p.write_text(content, encoding="utf-8")
    # 重新解析以保证 name/description 与落盘一致
    final_name, final_desc = _parse_skill_metadata(name, content)
    final_name = _validate_name(final_name)
    skill = SkillDefinition(
        name=final_name,
        description=description or final_desc,
        content=content,
        source="user",
        path=str(p),
        base_dir=str(skill_dir),
        command_name=name,
        display_name=final_name if final_name != name else None,
    )
    get_skill_registry().register(skill)
    return skill
