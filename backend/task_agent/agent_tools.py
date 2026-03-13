"""
Agent tools for Executor: ReadArtifact, ReadFile, ListFiles, WriteFile, Finish, ListSkills, LoadSkill, ReadSkillFile, RunSkillScript.
OpenAI function-calling format.
"""

import asyncio
import json
import os
import shlex
from pathlib import Path
from typing import Any, List, Optional, Tuple

import orjson

from db import DB_DIR, _validate_idea_id, _validate_plan_id, get_execution_task_src_dir, get_sandbox_dir, get_task_artifact
from shared.skill_utils import (
    list_skills as _list_skills,
    load_skill as _load_skill,
    parse_skill_frontmatter,
    read_skill_file as _read_skill_file,
)

from . import web_tools
from .docker_runtime import run_command_in_container, run_skill_script_in_container

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


def _get_plan_dir_path(idea_id: str, plan_id: str) -> Path:
    """Return absolute path to db/{idea_id}/{plan_id}/. Validates idea_id and plan_id, prevents path traversal."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return (DB_DIR / idea_id / plan_id).resolve()


def _get_task_root_dir(idea_id: str, plan_id: str, task_id: str, execution_run_id: str = "") -> Path:
    if execution_run_id:
        return get_execution_task_src_dir(execution_run_id, task_id).resolve()
    return get_sandbox_dir(idea_id, plan_id, task_id)


def _normalize_sandbox_subpath(path: str) -> tuple[str, str]:
    normalized = (path or "").replace("\\", "/").strip()
    if not normalized.startswith("sandbox/"):
        return normalized, ""
    subpath = normalized[7:].lstrip("/")
    return normalized, subpath


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
            "description": "Read a file. Use 'sandbox/...' for files in this task's sandbox (e.g. sandbox/result.txt).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path under sandbox, e.g. sandbox/result.txt or sandbox/data/output.json",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ListFiles",
            "description": "List files/directories under a path. Use 'sandbox/' to discover available files before ReadFile.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list. Prefer sandbox paths (e.g. sandbox/ or sandbox/data).",
                        "default": "sandbox/",
                    },
                    "max_entries": {
                        "type": "integer",
                        "description": "Maximum entries to return (default 200, max 500)",
                        "default": 200,
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum traversal depth (default 3, max 8)",
                        "default": 3,
                    },
                },
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
            "name": "RunCommand",
            "description": "Run a shell command inside the local Docker execution container using the current task sandbox as the working directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to run inside Docker, e.g. 'python script.py' or 'ls -la'",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Optional timeout in seconds (default 120)",
                        "default": 120,
                    },
                },
                "required": ["command"],
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
            "description": "Execute a script from a skill. Use for docx/pptx/xlsx validation, conversion, etc. Script runs from skill dir. Use [[sandbox]]/filename in args for sandbox file paths (e.g. [[sandbox]]/output.docx).",
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
                        "description": "Command-line args. Use [[sandbox]]/file.docx for sandbox file paths.",
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


async def run_read_artifact(idea_id: str, plan_id: str, task_id: str) -> str:
    """Execute ReadArtifact. Returns content string or error message."""
    try:
        if not task_id or not isinstance(task_id, str):
            return "Error: task_id must be a non-empty string"
        if ".." in task_id or "/" in task_id or "\\" in task_id:
            return "Error: task_id must not contain path separators"
        value = await get_task_artifact(idea_id, plan_id, task_id)
        if value is None:
            return f"Error: Task '{task_id}' has no output yet (not completed or does not exist)."
        try:
            return orjson.dumps(value, option=orjson.OPT_INDENT_2).decode("utf-8")
        except (TypeError, ValueError):
            return str(value)
    except Exception as e:
        return f"Error reading artifact: {e}"


async def run_read_file(idea_id: str, plan_id: str, path: str, task_id: str = "", execution_run_id: str = "", docker_container_name: str = "") -> str:
    """Execute ReadFile. In execution mode only sandbox paths are allowed. Returns content or error."""
    try:
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        path, subpath = _normalize_sandbox_subpath(path)
        if ".." in path:
            return "Error: path traversal not allowed"
        if execution_run_id and not path.startswith("sandbox/"):
            return "Error: execution-mode ReadFile only supports sandbox paths"
        if path.startswith("sandbox/") and execution_run_id and docker_container_name:
            if not task_id:
                return "Error: sandbox path requires task context"
            if not subpath:
                return "Error: sandbox path must include filename"
            import base64
            import shlex

            target_path = f"/workdir/src/{subpath}"
            cmd = f"cat {shlex.quote(target_path)} | base64"
            result = await run_command_in_container(
                container_name=docker_container_name,
                command=cmd,
                workdir="/workdir/src",
            )
            if result.get("code") != 0:
                return f"Error reading file from docker: {result.get('stderr')}"
            out_b64 = result.get("stdout", "").strip()
            try:
                return base64.b64decode(out_b64).decode("utf-8", errors="replace")
            except Exception as e:
                return f"Error decoding file from docker: {str(e)}"

        plan_dir = _get_plan_dir_path(idea_id, plan_id)
        if path.startswith("sandbox/"):
            if not task_id:
                return "Error: sandbox path requires task context"
            sandbox_dir = _get_task_root_dir(idea_id, plan_id, task_id, execution_run_id)
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


async def run_write_file(idea_id: str, plan_id: str, path: str, content: str, task_id: str = "", execution_run_id: str = "", docker_container_name: str = "") -> str:
    """Execute WriteFile. Path must be under sandbox. Returns success or error."""
    try:
        if not task_id:
            return "Error: WriteFile requires task context"
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        path, subpath = _normalize_sandbox_subpath(path)
        if ".." in path or not path.startswith("sandbox/"):
            return "Error: path must be under sandbox (e.g. sandbox/notes.txt)"
        if not subpath:
            return "Error: path must include filename"

        if execution_run_id and docker_container_name:
            import base64
            import shlex
            from pathlib import Path as PyPath
            target_path = f"/workdir/src/{subpath}"
            parent_dir = str(PyPath(target_path).parent).replace('\\', '/')
            content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            cmd = f"mkdir -p {shlex.quote(parent_dir)} && echo {content_b64} | base64 -d > {shlex.quote(target_path)}"
            result = await run_command_in_container(
                container_name=docker_container_name, command=cmd, workdir="/workdir/src"
            )
            if result.get("code") != 0:
                return f"Error writing file in docker: {result.get('stderr')}"
            return "OK"

        sandbox_dir = _get_task_root_dir(idea_id, plan_id, task_id, execution_run_id)
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


async def run_list_files(
    idea_id: str,
    plan_id: str,
    path: str,
    task_id: str = "",
    execution_run_id: str = "",
    docker_container_name: str = "",
    max_entries: int = 200,
    max_depth: int = 3,
) -> str:
    """Execute ListFiles. In execution mode only sandbox paths are allowed. Returns JSON listing or error."""
    try:
        normalized_path = (path or "sandbox/").strip() or "sandbox/"
        normalized_path, subpath = _normalize_sandbox_subpath(normalized_path)
        if ".." in normalized_path:
            return "Error: path traversal not allowed"

        max_entries = max(1, min(int(max_entries or 200), 500))
        max_depth = max(0, min(int(max_depth or 3), 8))

        if execution_run_id and not normalized_path.startswith("sandbox/"):
            return "Error: execution-mode ListFiles only supports sandbox paths"

        if execution_run_id and docker_container_name:
            if not task_id:
                return "Error: sandbox path requires task context"
            target_path = "/workdir/src"
            if subpath:
                target_path = f"/workdir/src/{subpath}"
            cmd = (
                f"if [ -d {shlex.quote(target_path)} ]; then "
                f"cd {shlex.quote(target_path)} && "
                f"find . -mindepth 1 -maxdepth {max_depth} | "
                "sed 's#^\\./##' | "
                f"head -n {max_entries}; "
                "else echo '__MAARS_NOT_FOUND_OR_DIR__'; fi"
            )
            result = await run_command_in_container(
                container_name=docker_container_name,
                command=cmd,
                workdir="/workdir/src",
                timeout_seconds=30,
            )
            if result.get("code") != 0:
                return f"Error listing files from docker: {result.get('stderr')}"
            stdout = (result.get("stdout") or "").strip()
            if stdout == "__MAARS_NOT_FOUND_OR_DIR__":
                return f"Error: Path not found or not a directory: {normalized_path}"
            items = [line.strip() for line in stdout.splitlines() if line.strip()]
            body = {
                "path": normalized_path,
                "count": len(items),
                "items": items,
                "truncated": len(items) >= max_entries,
            }
            return orjson.dumps(body, option=orjson.OPT_INDENT_2).decode("utf-8")

        plan_dir = _get_plan_dir_path(idea_id, plan_id)
        if normalized_path.startswith("sandbox/"):
            if not task_id:
                return "Error: sandbox path requires task context"
            sandbox_dir = _get_task_root_dir(idea_id, plan_id, task_id, execution_run_id)
            target_dir = sandbox_dir if not subpath else (sandbox_dir / subpath).resolve()
            try:
                target_dir.relative_to(sandbox_dir.resolve())
            except ValueError:
                return "Error: path traversal not allowed"
        else:
            target_dir = (plan_dir / normalized_path).resolve()
            try:
                target_dir.relative_to(plan_dir)
            except ValueError:
                return "Error: path traversal not allowed"

        if not target_dir.exists():
            return f"Error: Path not found: {normalized_path}"
        if not target_dir.is_dir():
            return f"Error: Not a directory: {normalized_path}"

        entries: list[str] = []
        base_parts = len(target_dir.parts)
        for item in sorted(target_dir.rglob("*"), key=lambda p: p.as_posix()):
            rel_parts = len(item.parts) - base_parts
            if rel_parts <= 0 or rel_parts > max_depth:
                continue
            rel = item.relative_to(target_dir).as_posix()
            entries.append(rel + ("/" if item.is_dir() else ""))
            if len(entries) >= max_entries:
                break

        body = {
            "path": normalized_path,
            "count": len(entries),
            "items": entries,
            "truncated": len(entries) >= max_entries,
        }
        return orjson.dumps(body, option=orjson.OPT_INDENT_2).decode("utf-8")
    except Exception as e:
        return f"Error listing files: {e}"


def run_list_skills() -> str:
    """Execute ListSkills. Returns JSON string of [{name, description}, ...] or error."""
    return _list_skills(SKILLS_ROOT)


def run_load_skill(name: str) -> str:
    """Execute LoadSkill. Returns SKILL.md full content or error."""
    return _load_skill(SKILLS_ROOT, name)


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
    return _read_skill_file(SKILLS_ROOT, skill, path)


async def run_run_skill_script(
    skill: str,
    script: str,
    args: List[str],
    idea_id: str,
    plan_id: str,
    task_id: str,
    execution_run_id: str = "",
    docker_container_name: str = "",
) -> str:
    """Execute RunSkillScript. Runs script from skill dir. [[sandbox]] or {{sandbox}} in args are replaced with sandbox path."""
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

        if execution_run_id and docker_container_name:
            result = await run_skill_script_in_container(
                container_name=docker_container_name,
                task_id=task_id,
                skill=skill,
                script_rel_path=script,
                args=[str(a) for a in (args or [])],
                timeout_seconds=_RUN_SCRIPT_TIMEOUT,
            )
            out = result.get("stdout", "")
            err = result.get("stderr", "")
            if result.get("code") != 0:
                return f"Exit code {result.get('code')}\nstdout:\n{out}\nstderr:\n{err}"
            return out + (f"\n{err}" if err else "")

        sandbox_dir = _get_task_root_dir(idea_id, plan_id, task_id, execution_run_id)
        sandbox_str = str(sandbox_dir.resolve())
        resolved_args = [
            (a.replace("[[sandbox]]", sandbox_str).replace("{{sandbox}}", sandbox_str) if isinstance(a, str) else str(a))
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


async def run_run_command(
    command: str,
    task_id: str,
    *,
    docker_container_name: str = "",
    timeout_seconds: int | None = None,
) -> str:
    try:
        cmd = (command or "").strip()
        if not cmd:
            return "Error: command must be a non-empty string"
        if not docker_container_name:
            return "Error: Docker execution container is not connected for this task"
        result = await run_command_in_container(
            container_name=docker_container_name,
            command=cmd,
            workdir="/workdir/src",
            timeout_seconds=timeout_seconds or _RUN_SCRIPT_TIMEOUT,
        )
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        if result.get("code") != 0:
            return f"Exit code {result.get('code')}\nstdout:\n{stdout}\nstderr:\n{stderr}"
        body = stdout.strip()
        if stderr.strip():
            body = (body + "\n" if body else "") + stderr.strip()
        return body or "OK"
    except Exception as e:
        return f"Error running command: {e}"


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
    name: str,
    arguments: str,
    idea_id: str,
    plan_id: str,
    task_id: str,
    *,
    execution_run_id: str = "",
    docker_container_name: str = "",
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
        result = await run_read_artifact(idea_id, plan_id, tid)
        return None, result

    if name == "ReadFile":
        path = args.get("path", "")
        result = await run_read_file(idea_id, plan_id, path, task_id, execution_run_id, docker_container_name)
        return None, result

    if name == "ListFiles":
        path = args.get("path", "sandbox/")
        max_entries = args.get("max_entries", 200)
        max_depth = args.get("max_depth", 3)
        result = await run_list_files(
            idea_id,
            plan_id,
            path,
            task_id,
            execution_run_id,
            docker_container_name,
            max_entries,
            max_depth,
        )
        return None, result

    if name == "WriteFile":
        path = args.get("path", "")
        content = args.get("content", "")
        result = await run_write_file(idea_id, plan_id, path, content, task_id, execution_run_id, docker_container_name)
        return None, result

    if name == "RunCommand":
        command = args.get("command", "")
        timeout_seconds = args.get("timeout_seconds")
        result = await run_run_command(
            command,
            task_id,
            docker_container_name=docker_container_name,
            timeout_seconds=timeout_seconds,
        )
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
        result = await run_run_skill_script(
            skill,
            script,
            script_args,
            idea_id,
            plan_id,
            task_id,
            execution_run_id=execution_run_id,
            docker_container_name=docker_container_name,
        )
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
