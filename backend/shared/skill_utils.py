"""Skill parsing and I/O utilities. Shared by Idea/Plan/Task Agent tools."""

import json
from pathlib import Path

import yaml


def parse_skill_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from SKILL.md. Returns dict with name, description, etc.

    Falls back to a simple line-by-line parser when yaml.safe_load fails (e.g. when
    the description value contains unquoted colons, which violates strict YAML).
    """
    import re
    if not content or "---" not in content:
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    raw = parts[1]
    try:
        result = yaml.safe_load(raw)
        return result or {}
    except yaml.YAMLError:
        pass

    def _supports_simple_fallback(value: str) -> bool:
        stripped = value.strip()
        if not stripped:
            return True
        # Only fall back for plain scalar-like values. If the value starts with YAML
        # collection / block syntax, parsing errors should be treated as invalid
        # frontmatter rather than silently accepting a truncated result.
        return not stripped.startswith(("[", "{", "|", ">", "&", "*", "!"))

    # Fallback: simple line-by-line key: value parser (handles unquoted colons in values)
    result: dict = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r'^(\w[\w-]*):\s*(.*)', line)
        if not m:
            return {}
        value = m.group(2).strip()
        if not _supports_simple_fallback(value):
            return {}
        result[m.group(1)] = value
    return result


def list_skills(skills_root: Path) -> str:
    """
    列出 skills_root 下的所有 skill。返回 JSON 字符串 [{name, description}, ...] 或错误信息。
    供 Idea/Plan/Task Agent 的 ListSkills 工具复用。
    """
    try:
        if not skills_root.exists() or not skills_root.is_dir():
            return json.dumps([])
        skills = []
        for item in sorted(skills_root.iterdir()):
            if not item.is_dir():
                continue
            skill_md = item / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                content = skill_md.read_text(encoding="utf-8", errors="replace")
                meta = parse_skill_frontmatter(content)
                name = meta.get("name") or item.name
                desc = meta.get("description") or ""
                skills.append({"name": name, "description": desc})
            except Exception:
                skills.append({"name": item.name, "description": ""})
        return json.dumps(skills, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error listing skills: {e}"


def load_skill(skills_root: Path, name: str) -> str:
    """
    加载 skill 的 SKILL.md 内容。返回内容或错误信息。
    供 Idea/Plan/Task Agent 的 LoadSkill 工具复用。
    """
    try:
        if not name or ".." in name or "/" in name or "\\" in name:
            return "Error: invalid skill name"
        skill_dir = (skills_root / name.strip()).resolve()
        try:
            skill_dir.relative_to(skills_root.resolve())
        except ValueError:
            return "Error: invalid skill name"
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists() or not skill_md.is_file():
            return f"Error: Skill '{name}' not found (no SKILL.md)"
        return skill_md.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error loading skill: {e}"


def read_skill_file(skills_root: Path, skill: str, path: str) -> str:
    """
    读取 skill 目录下的文件。返回内容或错误信息。
    供 Idea/Plan/Task Agent 的 ReadSkillFile 工具复用。
    """
    try:
        if not skill or ".." in skill or "/" in skill or "\\" in skill:
            return "Error: invalid skill name"
        skill_dir = (skills_root / skill.strip()).resolve()
        try:
            skill_dir.relative_to(skills_root.resolve())
        except ValueError:
            return "Error: invalid skill name"
        path = path.replace("\\", "/").strip()
        if ".." in path or path.startswith("/"):
            return "Error: path traversal not allowed"
        full = (skill_dir / path).resolve()
        try:
            full.relative_to(skill_dir)
        except ValueError:
            return "Error: path traversal not allowed"
        if not full.exists():
            return f"Error: File not found: {path}"
        if not full.is_file():
            return "Error: Not a file"
        return full.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading skill file: {e}"
