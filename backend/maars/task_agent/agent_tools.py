"""
Agent tools for Executor: ReadArtifact, ReadFile, WriteFile, Finish, ListSkills, LoadSkill, ReadSkillFile, RunSkillScript.
OpenAI function-calling format.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, List, Optional, Tuple

import orjson

from db import DB_DIR, _validate_plan_id, get_sandbox_dir, get_task_artifact
from shared.skill_utils import parse_skill_frontmatter

from . import web_tools

# RunSkillScript: allowed extensions, timeout (seconds, configurable via env)
_RUN_SCRIPT_ALLOWED_EXT = (".py", ".sh", ".js")
_RUN_SCRIPT_TIMEOUT = int(os.environ.get("MAARS_RUN_SCRIPT_TIMEOUT", "120"))

# Skills root: MAARS_TASK_SKILLS_DIR env or backend/task_agent/skills/
_TASK_SKILLS_DIR = os.environ.get("MAARS_TASK_SKILLS_DIR")
SKILLS_ROOT = (
    Path(_TASK_SKILLS_DIR).resolve()
    if _TASK_SKILLS_DIR
    else Path(__file__).resolve().parent / "skills"
)


def _get_plan_dir_path(plan_id: str) -> Path:
    """Return absolute path to db/{plan_id}/. Validates plan_id, prevents path traversal."""
    _validate_plan_id(plan_id)
    return (DB_DIR / plan_id).resolve()


# OpenAI function-calling tool definitions
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ReadArtifact",
            "description": "Read output artifact from a dependency task. Use when you need the output of another task that this task depends on.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID whose output to read (e.g. from dependencies)",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ReadFile",
            "description": "Read a file. Use 'sandbox/...' for files in this task's sandbox (e.g. sandbox/result.txt), or a path relative to plan dir for shared files (e.g. 'plan.json', 'task_1/output.json').",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path: 'sandbox/X' for sandbox files, or 'X' for plan dir (e.g. plan.json, task_id/output.json)",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "WriteFile",
            "description": "Write content to a file in this task's sandbox. Path must be under sandbox (e.g. sandbox/notes.txt). Use for intermediate results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path under sandbox, e.g. sandbox/data.json or sandbox/notes.txt",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Finish",
            "description": "Submit the final output and complete the task. Call this when output satisfies the output spec. For JSON format pass an object; for Markdown pass a string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "output": {
                        "type": "string",
                        "description": "Final output: JSON string or Markdown content. For JSON format, pass a valid JSON string.",
                    },
                },
                "required": ["output"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ListSkills",
            "description": "List available Agent Skills (name and description). Use to discover skills before loading one with LoadSkill.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "LoadSkill",
            "description": "Load a skill's SKILL.md full content into context. Call after ListSkills to get the skill name. The content will be available in the next turn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill name (directory name under skills root, e.g. from ListSkills)",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ReadSkillFile",
            "description": "Read a file from a skill's directory (scripts/, references/, assets/). Use after LoadSkill when you need to read a specific file from the skill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill": {
                        "type": "string",
                        "description": "Skill name (e.g. docx, pptx)",
                    },
                    "path": {
                        "type": "string",
                        "description": "Path relative to skill dir, e.g. scripts/office/unpack.py or references/example.md",
                    },
                },
                "required": ["skill", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "RunSkillScript",
            "description": "Execute a script from a skill. Use for docx/pptx/xlsx validation, conversion, etc. Script runs from skill dir. Use {{sandbox}}/filename in args for sandbox file paths (e.g. {{sandbox}}/output.docx).",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill": {
                        "type": "string",
                        "description": "Skill name (e.g. docx, pptx, xlsx)",
                    },
                    "script": {
                        "type": "string",
                        "description": "Path to script relative to skill dir, e.g. scripts/office/validate.py",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Command-line args. Use {{sandbox}}/file.docx for sandbox file paths.",
                    },
                },
                "required": ["skill", "script"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "WebSearch",
            "description": "Search the web for information. Use for research tasks when you need current data, benchmarks, or official documentation. Returns title, URL, and snippet for each result. Prefer WebSearch then WebFetch for key URLs to cite sources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g. 'FastAPI performance benchmark RPS', 'Django vs Flask comparison 2024')",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default 5, max 10)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "WebFetch",
            "description": "Fetch content from a URL. Use after WebSearch to get full page content for citations. Only http/https URLs; no localhost.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL to fetch (e.g. https://fastapi.tiangolo.com)",
                    },
                },
                "required": ["url"],
            },
        },
    },
]


async def run_read_artifact(plan_id: str, task_id: str) -> str:
    """Execute ReadArtifact. Returns content string or error message."""
    try:
        if not task_id or not isinstance(task_id, str):
            return "Error: task_id must be a non-empty string"
        if ".." in task_id or "/" in task_id or "\\" in task_id:
            return "Error: task_id must not contain path separators"
        value = await get_task_artifact(plan_id, task_id)
        if value is None:
            return f"Error: Task '{task_id}' has no output yet (not completed or does not exist)."
        try:
            return orjson.dumps(value, option=orjson.OPT_INDENT_2).decode("utf-8")
        except (TypeError, ValueError):
            return str(value)
    except Exception as e:
        return f"Error reading artifact: {e}"


async def run_read_file(plan_id: str, path: str, task_id: str = "") -> str:
    """Execute ReadFile. Path: 'sandbox/X' for sandbox, or 'X' for plan dir. Returns content or error."""
    try:
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        path = path.replace("\\", "/").strip()
        if ".." in path:
            return "Error: path traversal not allowed"
        plan_dir = _get_plan_dir_path(plan_id)
        if path.startswith("sandbox/"):
            if not task_id:
                return "Error: sandbox path requires task context"
            sandbox_dir = get_sandbox_dir(plan_id, task_id)
            subpath = path[7:].lstrip("/")  # after "sandbox/"
            if not subpath:
                return "Error: sandbox path must include filename"
            full = (sandbox_dir / subpath).resolve()
            try:
                full.relative_to(sandbox_dir.resolve())
            except ValueError:
                return "Error: path traversal not allowed"
        else:
            full = (plan_dir / path).resolve()
            try:
                full.relative_to(plan_dir)
            except ValueError:
                return "Error: path traversal not allowed"
        if not full.exists():
            return f"Error: File not found: {path}"
        if not full.is_file():
            return f"Error: Not a file: {path}"
        content = full.read_text(encoding="utf-8", errors="replace")
        return content
    except Exception as e:
        return f"Error reading file: {e}"


async def run_write_file(plan_id: str, path: str, content: str, task_id: str = "") -> str:
    """Execute WriteFile. Path must be under sandbox. Returns success or error."""
    try:
        if not task_id:
            return "Error: WriteFile requires task context"
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        path = path.replace("\\", "/").strip()
        if ".." in path or not path.startswith("sandbox/"):
            return "Error: path must be under sandbox (e.g. sandbox/notes.txt)"
        sandbox_dir = get_sandbox_dir(plan_id, task_id)
        subpath = path[7:].lstrip("/")
        if not subpath:
            return "Error: path must include filename"
        full = (sandbox_dir / subpath).resolve()
        try:
            full.relative_to(sandbox_dir.resolve())
        except ValueError:
            return "Error: path traversal not allowed"
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content or "", encoding="utf-8")
        return "OK"
    except Exception as e:
        return f"Error writing file: {e}"


def run_list_skills() -> str:
    """Execute ListSkills. Returns JSON string of [{name, description}, ...] or error."""
    try:
        if not SKILLS_ROOT.exists() or not SKILLS_ROOT.is_dir():
            return orjson.dumps([]).decode("utf-8")
        skills = []
        for item in sorted(SKILLS_ROOT.iterdir()):
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
        return orjson.dumps(skills, option=orjson.OPT_INDENT_2).decode("utf-8")
    except Exception as e:
        return f"Error listing skills: {e}"


def run_load_skill(name: str) -> str:
    """Execute LoadSkill. Returns SKILL.md full content or error."""
    try:
        if not name or not isinstance(name, str):
            return "Error: skill name must be a non-empty string"
        # Prevent path traversal: name must be safe (no .., /, \)
        if ".." in name or "/" in name or "\\" in name:
            return "Error: invalid skill name"
        skill_dir = (SKILLS_ROOT / name.strip()).resolve()
        try:
            skill_dir.relative_to(SKILLS_ROOT.resolve())
        except ValueError:
            return "Error: invalid skill name"
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists() or not skill_md.is_file():
            return f"Error: Skill '{name}' not found (no SKILL.md)"
        return skill_md.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error loading skill: {e}"


def _get_skill_dir(skill_name: str) -> Tuple[Optional[Path], str]:
    """Return (skill_dir, error_msg). error_msg non-empty on failure."""
    if not skill_name or not isinstance(skill_name, str):
        return None, "Error: skill name must be a non-empty string"
    if ".." in skill_name or "/" in skill_name or "\\" in skill_name:
        return None, "Error: invalid skill name"
    skill_dir = (SKILLS_ROOT / skill_name.strip()).resolve()
    try:
        skill_dir.relative_to(SKILLS_ROOT.resolve())
    except ValueError:
        return None, "Error: invalid skill name"
    if not skill_dir.exists() or not skill_dir.is_dir():
        return None, f"Error: Skill '{skill_name}' not found"
    return skill_dir, ""


def run_read_skill_file(skill: str, path: str) -> str:
    """Execute ReadSkillFile. Returns file content or error."""
    try:
        skill_dir, err = _get_skill_dir(skill)
        if err:
            return err
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
            return f"Error: Not a file: {path}"
        return full.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading skill file: {e}"


async def run_run_skill_script(
    skill: str, script: str, args: List[str], plan_id: str, task_id: str
) -> str:
    """Execute RunSkillScript. Runs script from skill dir. {{sandbox}} in args replaced with sandbox path."""
    try:
        skill_dir, err = _get_skill_dir(skill)
        if err:
            return err
        script = script.replace("\\", "/").strip()
        if ".." in script or script.startswith("/"):
            return "Error: script path traversal not allowed"
        script_path = (skill_dir / script).resolve()
        try:
            script_path.relative_to(skill_dir)
        except ValueError:
            return "Error: script path traversal not allowed"
        if not script_path.exists() or not script_path.is_file():
            return f"Error: Script not found: {script}"
        ext = script_path.suffix.lower()
        if ext not in _RUN_SCRIPT_ALLOWED_EXT:
            return f"Error: Script extension .{ext} not allowed (use .py, .sh, .js)"

        sandbox_dir = get_sandbox_dir(plan_id, task_id)
        sandbox_str = str(sandbox_dir.resolve())
        resolved_args = [
            a.replace("{{sandbox}}", sandbox_str) if isinstance(a, str) else str(a)
            for a in (args or [])
        ]

        if ext == ".py":
            cmd = ["python", str(script_path)] + resolved_args
        elif ext == ".sh":
            cmd = ["sh", str(script_path)] + resolved_args
        elif ext == ".js":
            cmd = ["node", str(script_path)] + resolved_args
        else:
            return f"Error: unsupported script type: {ext}"

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(skill_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_RUN_SCRIPT_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return f"Error: Script timed out after {_RUN_SCRIPT_TIMEOUT}s"

        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            return f"Exit code {proc.returncode}\nstdout:\n{out}\nstderr:\n{err}"
        return out + (f"\n{err}" if err else "")
    except Exception as e:
        return f"Error running script: {e}"


def run_finish(output: str) -> Tuple[bool, Any]:
    """
    Execute Finish. Returns (True, parsed_output) on success; (False, error_msg) on parse failure.
    output: JSON string or Markdown. For JSON we parse to dict.
    """
    if output is None or (isinstance(output, str) and not output.strip()):
        return False, "Error: output cannot be empty"
    s = output.strip() if isinstance(output, str) else str(output)
    # Try JSON first
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return True, parsed
        return True, {"content": parsed}
    except json.JSONDecodeError:
        pass
    # Treat as Markdown
    return True, {"content": s}


async def execute_tool(
    name: str, arguments: str, plan_id: str, task_id: str
) -> Tuple[Optional[Any], str]:
    """
    Execute a tool by name. Returns (finished_output, tool_result_str).
    - finished_output: None normally; dict/str when Finish succeeds (caller should exit loop)
    - tool_result_str: string to put in tool message (for ReadArtifact/ReadFile) or error
    """
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
    except json.JSONDecodeError as e:
        return None, f"Error: invalid tool arguments: {e}"

    if name == "ReadArtifact":
        tid = args.get("task_id", "")
        result = await run_read_artifact(plan_id, tid)
        return None, result

    if name == "ReadFile":
        path = args.get("path", "")
        result = await run_read_file(plan_id, path, task_id)
        return None, result

    if name == "WriteFile":
        path = args.get("path", "")
        content = args.get("content", "")
        result = await run_write_file(plan_id, path, content, task_id)
        return None, result

    if name == "ListSkills":
        result = run_list_skills()
        return None, result

    if name == "LoadSkill":
        skill_name = args.get("name", "")
        result = run_load_skill(skill_name)
        return None, result

    if name == "ReadSkillFile":
        skill = args.get("skill", "")
        path = args.get("path", "")
        result = run_read_skill_file(skill, path)
        return None, result

    if name == "RunSkillScript":
        skill = args.get("skill", "")
        script = args.get("script", "")
        script_args = args.get("args") or []
        if isinstance(script_args, str):
            try:
                script_args = json.loads(script_args) if script_args else []
            except json.JSONDecodeError:
                script_args = [script_args]
        result = await run_run_skill_script(skill, script, script_args, plan_id, task_id)
        return None, result

    if name == "Finish":
        out = args.get("output", "")
        ok, val = run_finish(out)
        if ok:
            return val, ""
        return None, val  # val is error message

    if name == "WebSearch":
        query = args.get("query", "")
        max_results = args.get("max_results", 5)
        result = await web_tools.run_web_search(query, max_results)
        return None, result

    if name == "WebFetch":
        url = args.get("url", "")
        result = await web_tools.run_web_fetch(url)
        return None, result

    return None, f"Error: unknown tool '{name}'"
