"""
Agent tools for Plan Agent: CheckAtomicity, Decompose, FormatTask, AddTasks, UpdateTask, GetPlan, GetNextTask, FinishPlan, ListSkills, LoadSkill, ReadSkillFile.
OpenAI function-calling format. Used when planAgentMode=True.
"""

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import orjson

from shared.graph import get_ancestor_path, get_parent_id
from shared.task_title import ensure_task_title
from shared.skill_utils import list_skills as _list_skills, load_skill as _load_skill, read_skill_file as _read_skill_file

# Plan skills root: MAARS_PLAN_SKILLS_DIR env or backend/plan_agent/skills/
_PLAN_SKILLS_DIR = os.environ.get("MAARS_PLAN_SKILLS_DIR")
PLAN_SKILLS_ROOT = (
    Path(_PLAN_SKILLS_DIR).resolve()
    if _PLAN_SKILLS_DIR
    else Path(__file__).resolve().parent / "skills"
)


def _find_task_idx(all_tasks: List[Dict], task_id: str) -> int:
    """Return index of task in all_tasks, or -1 if not found."""
    return next((i for i, t in enumerate(all_tasks) if t.get("task_id") == task_id), -1)


def _plan_agent_list_skills() -> str:
    """List Plan Agent skills. Returns JSON string of [{name, description}, ...]."""
    return _list_skills(PLAN_SKILLS_ROOT)


def _plan_agent_load_skill(name: str) -> str:
    """Load Plan Agent skill SKILL.md content."""
    return _load_skill(PLAN_SKILLS_ROOT, name)


def _plan_agent_read_skill_file(skill: str, path: str) -> str:
    """Read file from Plan Agent skill directory."""
    return _read_skill_file(PLAN_SKILLS_ROOT, skill, path)


# OpenAI function-calling tool definitions
PLAN_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "CheckAtomicity",
            "description": "Check if a task is atomic (executable in one step, clear outcome, no sub-phases). Call this first for each task before deciding to Decompose or FormatTask.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID to check (e.g. 0, 1, 1_1)"},
                    "description": {"type": "string", "description": "Task description"},
                    "context": {
                        "type": "object",
                        "description": "Optional context: depth (int), ancestor_path (str), idea (str), siblings (list of {task_id, description})",
                        "properties": {
                            "depth": {"type": "integer"},
                            "ancestor_path": {"type": "string"},
                            "idea": {"type": "string"},
                            "siblings": {"type": "array", "items": {"type": "object"}},
                        },
                    },
                },
                "required": ["task_id", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Decompose",
            "description": "Decompose a non-atomic task into child tasks. Call only when CheckAtomicity returned atomic=false.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Parent task ID"},
                    "description": {"type": "string", "description": "Parent task description"},
                    "context": {
                        "type": "object",
                        "description": "Optional context: depth, ancestor_path, idea, siblings",
                        "properties": {
                            "depth": {"type": "integer"},
                            "ancestor_path": {"type": "string"},
                            "idea": {"type": "string"},
                            "siblings": {"type": "array", "items": {"type": "object"}},
                        },
                    },
                },
                "required": ["task_id", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "FormatTask",
            "description": "Generate input/output specification for an atomic task. Call only when CheckAtomicity returned atomic=true.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                    "description": {"type": "string", "description": "Task description"},
                },
                "required": ["task_id", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "AddTasks",
            "description": "Add child tasks to the plan after Decompose. Each task must have task_id, title, description, dependencies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "parent_id": {"type": "string", "description": "Parent task ID (e.g. 0, 1)"},
                    "tasks": {
                        "type": "array",
                        "description": "List of {task_id, title, description, dependencies}. title is a 2-4 word phrase capturing the phase's core logic.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "task_id": {"type": "string"},
                                "title": {"type": "string", "description": "2-4 word title capturing the task's core logic (e.g. 'Data Collection', 'Model Training', '定义范围')"},
                                "description": {"type": "string"},
                                "dependencies": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["task_id", "title", "description", "dependencies"],
                        },
                    },
                },
                "required": ["parent_id", "tasks"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "UpdateTask",
            "description": "Update a task with input/output/validation from FormatTask. Call after FormatTask for atomic tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID to update"},
                    "input": {"type": "object", "description": "Input spec from FormatTask"},
                    "output": {"type": "object", "description": "Output spec from FormatTask"},
                    "validation": {"type": "object", "description": "Optional validation spec"},
                },
                "required": ["task_id", "input", "output"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "GetPlan",
            "description": "Get current plan state: all tasks and pending queue. Use to understand progress.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "GetNextTask",
            "description": "Get the next task to process from the pending queue. Returns null when queue is empty (all tasks processed).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "FinishPlan",
            "description": "Call when all tasks have been processed (GetNextTask returns null). Completes the planning phase.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ListSkills",
            "description": "List available Plan Agent Skills (decomposition patterns, research scoping, format specs). Use to discover skills before LoadSkill.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "LoadSkill",
            "description": "Load a Plan Agent skill's SKILL.md content. Use when you need reference for decomposition, scoping, or formatting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name (e.g. decomposition-patterns, research-scoping, format-specs)"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ReadSkillFile",
            "description": "Read a file from a Plan Agent skill (references/, scripts/). Use after LoadSkill when you need a specific file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string", "description": "Skill name"},
                    "path": {"type": "string", "description": "Path relative to skill dir, e.g. references/example.md"},
                },
                "required": ["skill", "path"],
            },
        },
    },
]


async def execute_plan_agent_tool(
    name: str,
    arguments: str,
    plan_state: Dict[str, Any],
    *,
    check_atomicity_fn: Callable,
    decompose_fn: Callable,
    format_fn: Callable,
    on_thinking: Optional[Callable] = None,
    on_tasks_batch: Optional[Callable] = None,
    abort_event: Optional[Any] = None,
    use_mock: bool = False,
    api_config: Optional[Dict] = None,
    idea_id: Optional[str] = None,
    plan_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Execute a Plan Agent tool by name. Returns (is_finish, result_str).
    - is_finish: True when FinishPlan is called; caller should exit agent loop.
    - result_str: JSON string to put in tool message.
    """
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
    except json.JSONDecodeError as e:
        return False, f"Error: invalid tool arguments: {e}"

    all_tasks = plan_state["all_tasks"]
    pending_queue = plan_state["pending_queue"]
    idea = plan_state.get("idea", "")

    if name == "GetNextTask":
        if not pending_queue:
            return False, orjson.dumps({"task_id": None, "task": None, "context": None}).decode("utf-8")
        tid = pending_queue.pop(0)
        idx = _find_task_idx(all_tasks, tid)
        task = all_tasks[idx] if idx >= 0 else {"task_id": tid, "description": "", "dependencies": []}
        parent_id = get_parent_id(tid)
        siblings = [t for t in all_tasks if t.get("task_id") != tid and get_parent_id(t.get("task_id", "")) == parent_id]
        depth = len(tid.split("_"))
        context = {
            "depth": depth,
            "ancestor_path": get_ancestor_path(tid),
            "idea": idea,
            "siblings": [{"task_id": t.get("task_id"), "description": (t.get("description") or "")[:80]} for t in siblings],
        }
        return False, orjson.dumps({"task_id": tid, "task": task, "context": context}).decode("utf-8")

    if name == "GetPlan":
        summary = []
        for t in all_tasks:
            tid = t.get("task_id", "")
            desc = (t.get("description", "") or "")[:60]
            has_io = "✓" if (t.get("input") and t.get("output")) else ""
            summary.append({"task_id": tid, "description": desc, "has_io": bool(has_io)})
        return False, orjson.dumps({
            "idea": idea,
            "tasks_count": len(all_tasks),
            "pending_count": len(pending_queue),
            "tasks": summary,
        }, option=orjson.OPT_INDENT_2).decode("utf-8")

    if name == "AddTasks":
        parent_id = args.get("parent_id", "")
        tasks = args.get("tasks", [])
        if not parent_id or not isinstance(tasks, list) or len(tasks) == 0:
            return False, 'Error: parent_id and non-empty tasks array required'
        for t in tasks:
            if not isinstance(t, dict) or not t.get("task_id") or not t.get("description"):
                return False, f'Error: each task must have task_id and description'
            deps = t.get("dependencies")
            if not isinstance(deps, list):
                t["dependencies"] = []
            ensure_task_title(t)
            all_tasks.append(t)
            pending_queue.append(t["task_id"])
        if on_tasks_batch:
            parent_task = next((x for x in all_tasks if x.get("task_id") == parent_id), {})
            on_tasks_batch(tasks, parent_task, list(all_tasks))
        return False, orjson.dumps({"added": len(tasks), "task_ids": [t["task_id"] for t in tasks]}).decode("utf-8")

    if name == "UpdateTask":
        task_id = args.get("task_id", "")
        input_spec = args.get("input")
        output_spec = args.get("output")
        validation = args.get("validation")
        if not task_id or not input_spec or not output_spec:
            return False, 'Error: task_id, input, output required'
        idx = _find_task_idx(all_tasks, task_id)
        if idx < 0:
            return False, f'Error: task {task_id} not found'
        all_tasks[idx]["input"] = input_spec
        all_tasks[idx]["output"] = output_spec
        if validation is not None:
            all_tasks[idx]["validation"] = validation
        return False, orjson.dumps({"updated": task_id}).decode("utf-8")

    if name == "FinishPlan":
        return True, orjson.dumps({"status": "complete", "tasks_count": len(all_tasks)}).decode("utf-8")

    if name == "CheckAtomicity":
        task_id = args.get("task_id", "")
        description = args.get("description", "")
        ctx = args.get("context") or {}
        task = {"task_id": task_id, "description": description, "dependencies": []}
        maybe_title = args.get("title")
        if isinstance(maybe_title, str) and maybe_title.strip():
            task["title"] = maybe_title.strip()
        ensure_task_title(task)
        siblings = ctx.get("siblings") or []
        depth = ctx.get("depth", 0)
        atomicity_context = {
            "depth": depth,
            "ancestor_path": ctx.get("ancestor_path") or get_ancestor_path(task_id),
            "idea": ctx.get("idea") or idea,
            "siblings": siblings,
        }
        try:
            result = await check_atomicity_fn(
                task, on_thinking, abort_event, atomicity_context, use_mock, api_config, idea_id, plan_id
            )
            return False, orjson.dumps({"atomic": result.get("atomic", False)}).decode("utf-8")
        except Exception as e:
            return False, f"Error: {e}"

    if name == "Decompose":
        task_id = args.get("task_id", "")
        description = args.get("description", "")
        ctx = args.get("context") or {}
        parent_task = {"task_id": task_id, "description": description, "dependencies": []}
        maybe_title = args.get("title")
        if isinstance(maybe_title, str) and maybe_title.strip():
            parent_task["title"] = maybe_title.strip()
        ensure_task_title(parent_task)
        depth = ctx.get("depth", 0)
        siblings = ctx.get("siblings") or []
        try:
            children = await decompose_fn(
                parent_task, on_thinking, abort_event, all_tasks,
                idea=idea, depth=depth, use_mock=use_mock, api_config=api_config, idea_id=idea_id, plan_id=plan_id,
            )
            return False, orjson.dumps({"tasks": children}).decode("utf-8")
        except Exception as e:
            return False, f"Error: {e}"

    if name == "FormatTask":
        task_id = args.get("task_id", "")
        description = args.get("description", "")
        task = {"task_id": task_id, "description": description, "dependencies": []}
        maybe_title = args.get("title")
        if isinstance(maybe_title, str) and maybe_title.strip():
            task["title"] = maybe_title.strip()
        ensure_task_title(task)
        try:
            result = await format_fn(
                task, on_thinking, abort_event, use_mock=use_mock, api_config=api_config, idea_id=idea_id, plan_id=plan_id,
            )
            if not result:
                return False, "Error: FormatTask returned no input/output"
            return False, orjson.dumps(result).decode("utf-8")
        except Exception as e:
            return False, f"Error: {e}"

    if name == "ListSkills":
        return False, _plan_agent_list_skills()

    if name == "LoadSkill":
        skill_name = args.get("name", "")
        return False, _plan_agent_load_skill(skill_name)

    if name == "ReadSkillFile":
        skill = args.get("skill", "")
        path = args.get("path", "")
        return False, _plan_agent_read_skill_file(skill, path)

    return False, f"Error: unknown tool '{name}'"
