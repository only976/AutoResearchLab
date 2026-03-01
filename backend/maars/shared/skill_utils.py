"""Skill parsing utilities. Shared by Plan Agent and Task Agent tools."""

import yaml


def parse_skill_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from SKILL.md. Returns dict with name, description, etc."""
    if not content or "---" not in content:
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
