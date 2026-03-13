import json

from shared.skill_utils import (
    list_skills,
    load_skill,
    parse_skill_frontmatter,
    read_skill_file,
)


def test_parse_skill_frontmatter_valid():
    content = """---
name: Demo
description: Hello
---
Body
"""
    meta = parse_skill_frontmatter(content)
    assert meta["name"] == "Demo"
    assert meta["description"] == "Hello"


def test_parse_skill_frontmatter_invalid_yaml_returns_empty():
    content = """---
name: [oops
---
Body
"""
    assert parse_skill_frontmatter(content) == {}


def test_list_skills_missing_dir_returns_empty_json(tmp_path):
    out = list_skills(tmp_path / "missing")
    assert json.loads(out) == []


def test_list_skills_reads_skills_and_frontmatter(tmp_path):
    skills_root = tmp_path / "skills"
    (skills_root / "alpha").mkdir(parents=True)
    (skills_root / "beta").mkdir(parents=True)

    (skills_root / "alpha" / "SKILL.md").write_text(
        """---
name: Alpha Skill
description: First
---
Content
""",
        encoding="utf-8",
    )
    (skills_root / "beta" / "SKILL.md").write_text("No frontmatter", encoding="utf-8")

    skills = json.loads(list_skills(skills_root))
    assert skills == [
        {"name": "Alpha Skill", "description": "First"},
        {"name": "beta", "description": ""},
    ]


def test_load_skill_rejects_path_traversal(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    assert load_skill(skills_root, "../x").startswith("Error: invalid skill name")
    assert load_skill(skills_root, "a/b").startswith("Error: invalid skill name")


def test_load_skill_reads_existing_skill(tmp_path):
    skills_root = tmp_path / "skills"
    (skills_root / "demo").mkdir(parents=True)
    (skills_root / "demo" / "SKILL.md").write_text("hi", encoding="utf-8")
    assert load_skill(skills_root, "demo") == "hi"


def test_read_skill_file_rejects_path_traversal(tmp_path):
    skills_root = tmp_path / "skills"
    (skills_root / "demo").mkdir(parents=True)
    (skills_root / "demo" / "SKILL.md").write_text("hi", encoding="utf-8")

    assert read_skill_file(skills_root, "demo", "../x").startswith("Error: path traversal not allowed")
    assert read_skill_file(skills_root, "demo", "/etc/passwd").startswith("Error: path traversal not allowed")


def test_read_skill_file_reads_nested_file(tmp_path):
    skills_root = tmp_path / "skills"
    (skills_root / "demo" / "files").mkdir(parents=True)
    (skills_root / "demo" / "SKILL.md").write_text("hi", encoding="utf-8")
    (skills_root / "demo" / "files" / "a.txt").write_text("ok", encoding="utf-8")

    assert read_skill_file(skills_root, "demo", "files/a.txt") == "ok"
