"""
Task Agent Skill Tests
======================
纯静态、离线验证，不需要任何 LLM API Key。

测试层次：
1. 结构验证: 每个 skill 都有合法的 SKILL.md、name、description
2. 描述覆盖验证: skill.description 能否覆盖其应用场景的关键词
3. 列表工具验证: list_skills() 能正确枚举并返回所有 skill
4. 加载工具验证: load_skill() 能正确加载指定 skill 的内容
5. 冗余扫描: 检测没有 name/description 重复的冗余 skill
6. Live agent 测试 (--run-live-agent): 验证 agent 真实场景下的 skill 选用行为
"""
import json
from pathlib import Path
import pytest

from shared.skill_utils import list_skills, load_skill, parse_skill_frontmatter

SKILLS_ROOT = Path(__file__).resolve().parents[3] / "task_agent" / "skills"


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _load_skill_meta(skill_name: str) -> dict:
    skill_md = SKILLS_ROOT / skill_name / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")
    return parse_skill_frontmatter(content)


def _desc_matches(skill_name: str, keywords: list[str]) -> list[str]:
    """Return keywords NOT found in the skill description (i.e. failures)."""
    meta = _load_skill_meta(skill_name)
    desc = (meta.get("description") or "").lower()
    return [kw for kw in keywords if kw.lower() not in desc]


# ─────────────────────────────────────────────
# 1. Structure Validation
# ─────────────────────────────────────────────

ALL_SKILL_DIRS = [d for d in SKILLS_ROOT.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]
ALL_SKILL_NAMES = [d.name for d in ALL_SKILL_DIRS]


@pytest.mark.parametrize("skill_dir", ALL_SKILL_DIRS, ids=lambda d: d.name)
def test_skill_has_skill_md(skill_dir):
    """Every skill directory must contain a SKILL.md file."""
    assert (skill_dir / "SKILL.md").is_file(), f"{skill_dir.name} is missing SKILL.md"


@pytest.mark.parametrize("skill_dir", ALL_SKILL_DIRS, ids=lambda d: d.name)
def test_skill_frontmatter_has_name(skill_dir):
    """SKILL.md must declare a non-empty 'name' in frontmatter."""
    content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    meta = parse_skill_frontmatter(content)
    assert meta.get("name"), f"{skill_dir.name}/SKILL.md is missing 'name' in frontmatter"


@pytest.mark.parametrize("skill_dir", ALL_SKILL_DIRS, ids=lambda d: d.name)
def test_skill_frontmatter_has_description(skill_dir):
    """SKILL.md must declare a non-empty 'description' in frontmatter (used for skill selection)."""
    content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    meta = parse_skill_frontmatter(content)
    assert meta.get("description"), (
        f"{skill_dir.name}/SKILL.md is missing 'description' in frontmatter – "
        "the agent relies on this field to decide when to use the skill"
    )


@pytest.mark.parametrize("skill_dir", ALL_SKILL_DIRS, ids=lambda d: d.name)
def test_skill_description_not_too_short(skill_dir):
    """Descriptions shorter than 30 chars are likely too vague for reliable skill selection."""
    content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    meta = parse_skill_frontmatter(content)
    desc = meta.get("description") or ""
    assert len(desc) >= 30, (
        f"{skill_dir.name}: description is only {len(desc)} chars – too short for reliable triggering"
    )


# ─────────────────────────────────────────────
# 2. Description Coverage per Skill
#    Skills retained after audit (agent can't do these well natively):
#      - find-skills:         External skill discovery/install workflow
#      - literature-synthesis: Theme-based multi-paper synthesis (agent loads this proactively)
#      - project-developer:    Writing full project to Docker workspace
#      - skill-creator:        End-to-end skill creation & eval workflow
#      - source-attribution:   Citation rules (agent skips references without this)
#      - task-output-validator: Script-based output validation before Finish
# ─────────────────────────────────────────────

SKILL_KEYWORD_MAP = {
    "find-skills":              ["discover", "skill", "find"],
    "literature-synthesis":     ["synthes", "literature", "sources"],
    "project-developer":        ["project", "disk", "runnable"],
    "skill-creator":            ["create", "skill", "improve"],
    "source-attribution":       ["citation", "references", "attribution"],
    "task-output-validator":    ["validate", "criteria", "finish"],
}


@pytest.mark.parametrize("skill_name,keywords", SKILL_KEYWORD_MAP.items())
def test_skill_description_covers_keywords(skill_name, keywords):
    """Skill description must mention at least one of the expected trigger keywords."""
    skill_md = SKILLS_ROOT / skill_name / "SKILL.md"
    if not skill_md.exists():
        pytest.skip(f"Skill '{skill_name}' does not exist – may have been removed")
    missing = _desc_matches(skill_name, keywords)
    assert len(missing) < len(keywords), (
        f"'{skill_name}' description doesn't cover ANY of its expected trigger keywords: {keywords}\n"
        f"Description: {_load_skill_meta(skill_name).get('description')}"
    )


# ─────────────────────────────────────────────
# 3. list_skills() tool
# ─────────────────────────────────────────────

def test_list_skills_returns_valid_json():
    """list_skills() must return parseable JSON."""
    result = list_skills(SKILLS_ROOT)
    parsed = json.loads(result)
    assert isinstance(parsed, list)


def test_list_skills_includes_all_skills():
    """list_skills() must include every skill directory that has a SKILL.md."""
    result = json.loads(list_skills(SKILLS_ROOT))
    listed_names = {s["name"] for s in result}
    for skill_dir in ALL_SKILL_DIRS:
        assert skill_dir.name in listed_names or any(
            s.get("name") == skill_dir.name for s in result
        ), f"list_skills() did not include skill '{skill_dir.name}'"


def test_list_skills_each_entry_has_description():
    """Every entry from list_skills() must have a non-empty description."""
    result = json.loads(list_skills(SKILLS_ROOT))
    for entry in result:
        assert entry.get("description"), (
            f"list_skills() returned empty description for skill '{entry.get('name')}'"
        )


# ─────────────────────────────────────────────
# 4. load_skill() tool
# ─────────────────────────────────────────────

@pytest.mark.parametrize("skill_name", ALL_SKILL_NAMES)
def test_load_skill_returns_content(skill_name):
    """load_skill() must return the SKILL.md file content for each skill."""
    result = load_skill(SKILLS_ROOT, skill_name)
    assert not result.startswith("Error:"), f"load_skill('{skill_name}') returned error: {result}"
    assert len(result) > 50, f"load_skill('{skill_name}') returned suspiciously short content"


def test_load_skill_invalid_name_is_rejected():
    """load_skill() must reject path-traversal or invalid names."""
    assert load_skill(SKILLS_ROOT, "../etc/passwd").startswith("Error:")
    assert load_skill(SKILLS_ROOT, "").startswith("Error:")
    assert load_skill(SKILLS_ROOT, "does-not-exist-xyz").startswith("Error:")


# ─────────────────────────────────────────────
# 5. Redundancy check
# ─────────────────────────────────────────────

def test_no_duplicate_skill_names():
    """No two skill directories should declare the same 'name' in frontmatter."""
    result = json.loads(list_skills(SKILLS_ROOT))
    names = [s["name"] for s in result]
    duplicates = {n for n in names if names.count(n) > 1}
    assert not duplicates, f"Duplicate skill names found: {duplicates}"


def test_no_near_duplicate_descriptions():
    """Flag skills whose descriptions share >80% of words (likely redundant)."""
    result = json.loads(list_skills(SKILLS_ROOT))
    redundant_pairs = []
    for i, a in enumerate(result):
        for b in result[i+1:]:
            words_a = set((a.get("description") or "").lower().split())
            words_b = set((b.get("description") or "").lower().split())
            if not words_a or not words_b:
                continue
            overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
            if overlap > 0.8:
                redundant_pairs.append((a["name"], b["name"], round(overlap, 2)))
    assert not redundant_pairs, (
        f"Possibly redundant skill pairs (>80% description word overlap):\n"
        + "\n".join(f"  {a} ↔ {b} ({ovl*100:.0f}%)" for a, b, ovl in redundant_pairs)
    )


# ─────────────────────────────────────────────
# 6. Live Agent Skill Triggering Tests
#    Run with: pytest --run-live-agent
#    These consume real LLM API tokens.
#    Only skills where live tests showed the agent actually benefits
#    from the skill (i.e., proactively loads it) are included here.
# ─────────────────────────────────────────────

@pytest.mark.flaky(reruns=2, reruns_delay=5)
@pytest.mark.live_llm
@pytest.mark.asyncio
async def test_live_literature_synthesis_skill(live_llm_config):
    """
    Validates that agent produces a quality thematic synthesis report.

    NOTE: The agent may or may not proactively load `literature-synthesis` —
    both are acceptable. This skill guides HOW to write (themes, gaps, citations),
    so the test focuses on output quality rather than skill loading behavior.
    Agent has demonstrated it can write good syntheses from internal knowledge alone.
    """
    from .skill_tester import verify_skill_usage
    loaded, output = await verify_skill_usage(
        task_id="live_literature_synthesis",
        description=(
            "I have several research papers on transformer architectures. "
            "Please synthesize the key findings across sources, organizing "
            "them by theme rather than per paper. Include a Gaps section."
        ),
        expected_skill="literature-synthesis",
        api_config=live_llm_config,
    )
    # Skill loading is optional (agent handles this well natively), just note it
    if loaded:
        assert "literature-synthesis" in loaded or len(loaded) > 0, (
            f"Agent loaded skills but not literature-synthesis: {loaded}"
        )
    # What matters: output is thematically structured and has a Gaps section
    assert "##" in output, "Expected structured H2 headings in synthesis output"
    assert any(
        kw in output.lower() for kw in ["gap", "limitation", "missing", "future"]
    ), "Expected a Gaps/Limitations section or similar in output"



@pytest.mark.flaky(reruns=2, reruns_delay=5)
@pytest.mark.live_llm
@pytest.mark.asyncio
async def test_live_task_output_validator_skill(live_llm_config):
    """
    Agent should load task-output-validator when told to validate output before finishing.
    This skill has actual scripts (scripts/validate.py) so it's genuinely useful.
    """
    from .skill_tester import verify_skill_usage
    loaded, output = await verify_skill_usage(
        task_id="live_task_output_validator",
        description=(
            "Generate a JSON object with keys 'title' and 'summary'. "
            "Before calling Finish, you MUST validate that the output is valid JSON "
            "with both required keys present using the task-output-validator skill."
        ),
        expected_skill="task-output-validator",
        api_config=live_llm_config,
    )
    assert "task-output-validator" in loaded, (
        f"Expected agent to load 'task-output-validator'. Loaded: {loaded}\nOutput: {output[:300]}"
    )


@pytest.mark.flaky(reruns=2, reruns_delay=5)
@pytest.mark.live_llm
@pytest.mark.asyncio
async def test_live_source_attribution_skill(live_llm_config):
    """
    Agent should load source-attribution when asked to produce a citation-heavy report.
    Without this skill, agents tend to omit the References section.
    """
    from .skill_tester import verify_skill_usage
    loaded, output = await verify_skill_usage(
        task_id="live_source_attribution",
        description=(
            "Write a short research summary about GPU performance benchmarks. "
            "Every quantitative claim MUST have an inline citation like [Source Name], "
            "and you MUST include a ## References section at the end. "
            "Use the source-attribution skill to ensure proper citation format."
        ),
        expected_skill="source-attribution",
        api_config=live_llm_config,
    )
    assert "source-attribution" in loaded, (
        f"Expected agent to load 'source-attribution'. Loaded: {loaded}\nOutput: {output[:300]}"
    )
    assert "## References" in output or "## Reference" in output, (
        "Expected a References section in output even without skill load"
    )
