"""Database Module.

Storage is SQLite-backed (see `db/sqlite_backend.py`), including settings.
"""

import asyncio
import json
import os
import re
import shutil
from pathlib import Path

import orjson
from loguru import logger

from . import sqlite_backend

DB_DIR = Path(__file__).parent
SANDBOX_DIR = Path(os.environ.get("MAARS_SANDBOX_DIR", str(DB_DIR.parent.parent / "sandbox"))).resolve()
DEFAULT_IDEA_ID = "test"
DEFAULT_PLAN_ID = "test"
SETTINGS_FILE = "settings.json"
_SETTINGS_KEY = "global"


def _validate_idea_id(idea_id: str) -> None:
    """Reject path traversal and invalid idea_id."""
    if not idea_id or not isinstance(idea_id, str):
        raise ValueError("idea_id must be a non-empty string")
    if ".." in idea_id or "/" in idea_id or "\\" in idea_id:
        raise ValueError("idea_id must not contain path separators")


def _validate_plan_id(plan_id: str) -> None:
    """Reject path traversal and invalid plan_id."""
    if not plan_id or not isinstance(plan_id, str):
        raise ValueError("plan_id must be a non-empty string")
    if ".." in plan_id or "/" in plan_id or "\\" in plan_id:
        raise ValueError("plan_id must not contain path separators")


def _validate_task_id(task_id: str) -> None:
    """Reject path traversal and invalid task_id. Only alphanumeric and underscore."""
    if not task_id or not isinstance(task_id, str):
        raise ValueError("task_id must be a non-empty string")
    if ".." in task_id or "/" in task_id or "\\" in task_id:
        raise ValueError("task_id must not contain path separators")
    if not re.match(r"^[a-zA-Z0-9_]+$", task_id):
        raise ValueError("task_id must contain only letters, digits, and underscores")


def _get_idea_dir(idea_id: str) -> Path:
    """Return db/{idea_id}/."""
    return DB_DIR / idea_id


def _get_plan_dir(idea_id: str, plan_id: str) -> Path:
    """Return db/{idea_id}/{plan_id}/."""
    return _get_idea_dir(idea_id) / plan_id


def _get_file_path(idea_id: str, plan_id: str, filename: str) -> Path:
    return _get_plan_dir(idea_id, plan_id) / filename


def _get_task_dir(idea_id: str, plan_id: str, task_id: str) -> Path:
    """Return db/{idea_id}/{plan_id}/{task_id}/."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    _validate_task_id(task_id)
    return _get_plan_dir(idea_id, plan_id) / task_id


def get_sandbox_dir(idea_id: str, plan_id: str, task_id: str) -> Path:
    """Return db/{idea_id}/{plan_id}/{task_id}/sandbox/ for isolated task execution."""
    return _get_task_dir(idea_id, plan_id, task_id) / "sandbox"


async def ensure_sandbox_dir(idea_id: str, plan_id: str, task_id: str) -> Path:
    """Create sandbox dir if not exists. Returns the sandbox path."""
    sandbox = get_sandbox_dir(idea_id, plan_id, task_id)
    sandbox.mkdir(parents=True, exist_ok=True)
    return sandbox


def get_execution_sandbox_root(execution_run_id: str) -> Path:
    """Return sandbox/{execution_run_id}/ for container-backed execution data."""
    if not execution_run_id or not isinstance(execution_run_id, str):
        raise ValueError("execution_run_id must be a non-empty string")
    if ".." in execution_run_id or "/" in execution_run_id or "\\" in execution_run_id:
        raise ValueError("execution_run_id must not contain path separators")
    return SANDBOX_DIR / execution_run_id


def get_execution_task_dir(execution_run_id: str, task_id: str) -> Path:
    """Return sandbox/{execution_run_id}/step/{task_id}/ for one task's step data."""
    _validate_task_id(task_id)
    return get_execution_sandbox_root(execution_run_id) / "step" / task_id


def get_execution_src_dir(execution_run_id: str) -> Path:
    """Return sandbox/{execution_run_id}/src/ shared by all tasks in one execution."""
    return get_execution_sandbox_root(execution_run_id) / "src"


def get_execution_step_root_dir(execution_run_id: str) -> Path:
    """Return sandbox/{execution_run_id}/step/ containing per-task step state."""
    return get_execution_sandbox_root(execution_run_id) / "step"


def get_execution_task_src_dir(execution_run_id: str, task_id: str) -> Path:
    _validate_task_id(task_id)
    return get_execution_src_dir(execution_run_id)


def get_execution_task_step_dir(execution_run_id: str, task_id: str) -> Path:
    return get_execution_task_dir(execution_run_id, task_id)


async def ensure_execution_task_dirs(execution_run_id: str, task_id: str) -> tuple[Path, Path]:
    src_dir = get_execution_src_dir(execution_run_id)
    step_dir = get_execution_task_step_dir(execution_run_id, task_id)
    src_dir.mkdir(parents=True, exist_ok=True)
    step_dir.mkdir(parents=True, exist_ok=True)
    return src_dir, step_dir


def _iter_execution_run_roots() -> list[Path]:
    if not SANDBOX_DIR.exists() or not SANDBOX_DIR.is_dir():
        return []
    return [p for p in SANDBOX_DIR.iterdir() if p.is_dir() and p.name.startswith("exec_")]


def find_execution_run_ids_for_research(idea_id: str | None, plan_id: str | None) -> list[str]:
    """Best-effort discovery of execution_run_ids for a given research (idea/plan)."""
    idea = str(idea_id or "").strip()
    plan = str(plan_id or "").strip()
    if not idea:
        return []

    matched: list[str] = []
    for run_root in _iter_execution_run_roots():
        run_id = run_root.name
        step_root = run_root / "step"
        if not step_root.exists() or not step_root.is_dir():
            continue
        found = False
        for meta in step_root.glob("*/container-meta.json"):
            try:
                payload = json.loads(meta.read_text(encoding="utf-8", errors="replace") or "{}")
            except Exception:
                continue
            if str(payload.get("ideaId") or "").strip() != idea:
                continue
            payload_plan = str(payload.get("planId") or "").strip()
            if plan and payload_plan and payload_plan != plan:
                continue
            found = True
            break
        if found:
            matched.append(run_id)
    return matched


def remove_execution_sandbox_root(execution_run_id: str) -> bool:
    try:
        path = get_execution_sandbox_root(execution_run_id)
    except Exception:
        return False
    if not path.exists():
        return False
    try:
        shutil.rmtree(path)
        return True
    except Exception as e:
        logger.warning("Failed to remove sandbox root {}: {}", path, e)
        return False


async def get_task_artifact(idea_id: str, plan_id: str, task_id: str):
    """Read task artifact. Returns dict or None."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    _validate_task_id(task_id)
    return await sqlite_backend.get_task_artifact(idea_id, plan_id, task_id)


async def list_plan_outputs(idea_id: str, plan_id: str) -> dict:
    """Load all task outputs for a plan. Returns {task_id: output_dict}."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return await sqlite_backend.list_plan_outputs(idea_id, plan_id)


async def save_task_artifact(idea_id: str, plan_id: str, task_id: str, value) -> dict:
    """Write task artifact."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    _validate_task_id(task_id)
    return await sqlite_backend.save_task_artifact(idea_id, plan_id, task_id, value)


async def delete_task_artifact(idea_id: str, plan_id: str, task_id: str) -> bool:
    """Remove task artifact. Returns True if deleted."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    _validate_task_id(task_id)
    return await sqlite_backend.delete_task_artifact(idea_id, plan_id, task_id)


async def save_validation_report(idea_id: str, plan_id: str, task_id: str, report: dict) -> dict:
    """Save task validation report."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    _validate_task_id(task_id)
    return await sqlite_backend.save_validation_report(idea_id, plan_id, task_id, report)


async def _ensure_idea_dir(idea_id: str = DEFAULT_IDEA_ID) -> None:
    # Legacy no-op: kept for backwards imports.
    _validate_idea_id(idea_id)
    return


async def _ensure_plan_dir(idea_id: str, plan_id: str) -> None:
    # Legacy no-op: kept for backwards imports.
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return


async def _read_json_file(idea_id: str, plan_id: str, filename: str):
    # Legacy: file-based helpers are no longer used.
    return None


async def _write_json_file(idea_id: str, plan_id: str, filename: str, data: dict) -> dict:
    # Legacy: file-based helpers are no longer used.
    return {"success": False}


# Idea persistence

async def get_idea(idea_id: str = DEFAULT_IDEA_ID):
    """Get idea (Refine output: idea, keywords, papers, etc.)."""
    _validate_idea_id(idea_id)
    return await sqlite_backend.get_idea(idea_id)


async def save_idea(idea_data: dict, idea_id: str = DEFAULT_IDEA_ID) -> dict:
    """Save idea to db/{idea_id}/idea.json."""
    _validate_idea_id(idea_id)
    return await sqlite_backend.save_idea(idea_id, idea_data)


# Plan and execution

async def get_execution(idea_id: str, plan_id: str):
    """Get execution."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return await sqlite_backend.get_execution(idea_id, plan_id)


async def save_execution(execution: dict, idea_id: str, plan_id: str) -> dict:
    """Save execution."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return await sqlite_backend.save_execution(idea_id, plan_id, execution)


async def list_idea_ids() -> list:
    """List idea IDs from db/, sorted by idea.json mtime (newest first)."""
    return await sqlite_backend.list_idea_ids()


async def list_plan_ids(idea_id: str) -> list:
    """List plan IDs under an idea, sorted by plan.json mtime (newest first)."""
    _validate_idea_id(idea_id)
    return await sqlite_backend.list_plan_ids(idea_id)


async def list_recent_plans() -> list:
    """List (ideaId, planId) pairs from db/, sorted by plan.json mtime (newest first)."""
    return await sqlite_backend.list_recent_plans()


def _resolve_config(raw: dict) -> dict:
    """
    解析 settings 为运行时 cfg。
    结构：preset（API 连接）+ agentMode（模式标志）。
    """
    if not raw:
        return {}
    agent_mode = raw.get("agentMode") or {}
    idea_m = agent_mode.get("ideaAgent") or "mock"
    plan_m = agent_mode.get("planAgent") or "mock"
    task_m = agent_mode.get("taskAgent") or "mock"
    paper_m = agent_mode.get("paperAgent") or "mock"

    presets = raw.get("presets")
    current = raw.get("current")
    if isinstance(presets, dict) and current and current in presets:
        cfg = dict(presets[current])
        cfg.pop("label", None)
        cfg.pop("phases", None)
    else:
        cfg = {}

    cfg["ideaUseMock"] = idea_m == "mock"
    cfg["planUseMock"] = plan_m == "mock"
    cfg["taskUseMock"] = task_m == "mock"
    cfg["paperUseMock"] = paper_m == "mock"
    cfg["ideaAgentMode"] = idea_m == "agent"
    cfg["planAgentMode"] = plan_m == "agent"
    cfg["taskAgentMode"] = task_m == "agent"
    cfg["paperAgentMode"] = paper_m == "agent"
    cfg["ideaUseRAG"] = bool(agent_mode.get("ideaRAG", False))

    reflection = raw.get("reflection") or {}
    cfg["reflectionEnabled"] = reflection.get("enabled", False)
    cfg["reflectionMaxIterations"] = reflection.get("maxIterations", 2)
    cfg["reflectionQualityThreshold"] = reflection.get("qualityThreshold", 70)

    return cfg


async def get_settings() -> dict:
    """Get full settings from SQLite. One-time legacy import from settings.json if needed."""
    settings = await sqlite_backend.get_settings(_SETTINGS_KEY)
    if settings:
        return settings

    legacy_file = DB_DIR / SETTINGS_FILE
    if not legacy_file.exists():
        return {}
    try:
        data = orjson.loads(legacy_file.read_bytes())
        if isinstance(data, dict) and data:
            await sqlite_backend.save_settings(data, _SETTINGS_KEY)
            return data
    except Exception as e:
        logger.warning("Failed legacy settings import from %s: %s", legacy_file, e)
    return {}


async def get_effective_config() -> dict:
    """Get effective config for LLM/plan/execution (resolves current preset from settings)."""
    raw = await get_settings()
    return _resolve_config(raw)


async def save_settings(settings: dict) -> dict:
    """Save settings to SQLite."""
    return await sqlite_backend.save_settings(settings or {}, _SETTINGS_KEY)


async def get_plan(idea_id: str, plan_id: str):
    """Get plan (tasks only, no idea)."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return await sqlite_backend.get_plan(idea_id, plan_id)


async def save_plan(plan: dict, idea_id: str, plan_id: str) -> dict:
    """Save plan."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return await sqlite_backend.save_plan(idea_id, plan_id, plan)


# AI response persistence (atomicity, decompose, format) - per idea_id + plan_id

_ai_save_locks: dict = {}


def _get_ai_save_lock(idea_id: str, plan_id: str, response_type: str) -> asyncio.Lock:
    key = (idea_id, plan_id, response_type)
    if key not in _ai_save_locks:
        _ai_save_locks[key] = asyncio.Lock()
    return _ai_save_locks[key]


async def _read_ai_response_file(idea_id: str, plan_id: str, response_type: str) -> dict:
    # Legacy: replaced by SQLite storage.
    return await sqlite_backend.get_ai_responses(idea_id, plan_id, response_type)


async def get_ai_responses(idea_id: str, plan_id: str, response_type: str) -> dict:
    """Read AI responses for a plan. response_type: atomicity, decompose, format."""
    if response_type not in ("atomicity", "decompose", "format"):
        return {}
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return await sqlite_backend.get_ai_responses(idea_id, plan_id, response_type)


async def _write_ai_response_file(idea_id: str, plan_id: str, response_type: str, data: dict) -> None:
    await sqlite_backend.save_ai_responses_blob(idea_id, plan_id, response_type, data)


async def save_ai_response(idea_id: str, plan_id: str, response_type: str, key: str, entry: dict) -> None:
    """Incrementally save one AI response. entry = {content: ..., reasoning: ...}. Serialized per file."""
    if response_type not in ("atomicity", "decompose", "format"):
        return
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    lock = _get_ai_save_lock(idea_id, plan_id, response_type)
    async with lock:
        data = await get_ai_responses(idea_id, plan_id, response_type)
        data[key] = entry
        await _write_ai_response_file(idea_id, plan_id, response_type, data)


async def clear_db() -> dict:
    """Clear DB runtime artifacts (ideas/plans/execution/research/papers). Keeps settings."""
    removed = []
    # Clear sqlite data first
    await sqlite_backend.clear_all_data()
    # Best-effort remove legacy folders for a fully clean slate.
    if DB_DIR.exists():
        for p in DB_DIR.iterdir():
            if not p.is_dir() or p.name.startswith("."):
                continue
            try:
                shutil.rmtree(p)
                removed.append(p.name)
            except OSError as e:
                logger.warning("Failed to remove %s: %s", p, e)
    if SANDBOX_DIR.exists() and SANDBOX_DIR.is_dir():
        for p in SANDBOX_DIR.iterdir():
            if not p.is_dir() or p.name.startswith("."):
                continue
            try:
                shutil.rmtree(p)
                removed.append(f"sandbox/{p.name}")
            except OSError as e:
                logger.warning("Failed to remove %s: %s", p, e)
    return {"success": True, "removed": removed}


# --- Research API helpers (SQLite) ---


async def create_research(research_id: str, prompt: str, title: str) -> None:
    return await sqlite_backend.create_research(research_id, prompt, title)


async def list_researches() -> list[dict]:
    return await sqlite_backend.list_researches()


async def get_research(research_id: str) -> dict | None:
    return await sqlite_backend.get_research(research_id)


async def update_research_stage(
    research_id: str,
    *,
    stage: str | None = None,
    stage_status: str | None = None,
    current_idea_id: str | None = None,
    current_plan_id: str | None = None,
    error: str | None = None,
) -> None:
    return await sqlite_backend.update_research_stage(
        research_id,
        stage=stage,
        stage_status=stage_status,
        current_idea_id=current_idea_id,
        current_plan_id=current_plan_id,
        error=error,
    )


async def save_paper(idea_id: str, plan_id: str, *, format_type: str, content: str) -> None:
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return await sqlite_backend.save_paper(idea_id, plan_id, format_type=format_type, content=content)


async def get_paper(idea_id: str, plan_id: str) -> dict | None:
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return await sqlite_backend.get_paper(idea_id, plan_id)


async def clear_research_stage_data_for_retry(idea_id: str | None, plan_id: str | None, stage: str) -> dict:
    """Clear current-stage and downstream data for retry; also removes matching execution sandbox runs."""
    idea = str(idea_id or "").strip()
    plan = str(plan_id or "").strip()
    result = await sqlite_backend.clear_research_stage_data_for_retry(idea, plan, stage)
    run_ids = find_execution_run_ids_for_research(idea, plan)
    removed_runs: list[str] = []
    for run_id in run_ids:
        if remove_execution_sandbox_root(run_id):
            removed_runs.append(run_id)
    result["executionRunIds"] = run_ids
    result["sandboxRunsRemoved"] = removed_runs
    return result


async def delete_research_cascade(research_id: str) -> dict:
    """Delete a research and all related data, including filesystem artifacts (sandbox directories)."""
    result = await sqlite_backend.delete_research_cascade(research_id)
    
    if not result.get("success"):
        return result
    
    # Delete filesystem artifacts if idea_id exists
    idea_id = result.get("ideaId")
    plan_id = result.get("planId")
    run_ids = find_execution_run_ids_for_research(idea_id, plan_id)
    removed_runs: list[str] = []
    for run_id in run_ids:
        if remove_execution_sandbox_root(run_id):
            removed_runs.append(run_id)
    result["executionRunIds"] = run_ids
    result["sandboxRunsRemoved"] = removed_runs

    if idea_id:
        idea_dir = _get_idea_dir(idea_id)
        if idea_dir.exists():
            try:
                shutil.rmtree(idea_dir)
                logger.info("Deleted filesystem artifacts for idea_id={}", idea_id)
            except Exception as e:
                logger.warning("Failed to delete directory {}: {}", idea_dir, e)
    
    return result


async def save_task_attempt_memory(research_id: str, task_id: str, attempt: int, value: dict) -> dict:
    if not research_id or not isinstance(research_id, str):
        raise ValueError("research_id must be a non-empty string")
    _validate_task_id(task_id)
    return await sqlite_backend.save_task_attempt_memory(research_id, task_id, attempt, value)


async def list_task_attempt_memories(research_id: str, task_id: str | None = None) -> list[dict]:
    if not research_id or not isinstance(research_id, str):
        raise ValueError("research_id must be a non-empty string")
    if task_id:
        _validate_task_id(task_id)
    return await sqlite_backend.list_task_attempt_memories(research_id, task_id)


async def delete_task_attempt_memories(research_id: str, task_id: str | None = None) -> int:
    if not research_id or not isinstance(research_id, str):
        raise ValueError("research_id must be a non-empty string")
    if task_id:
        _validate_task_id(task_id)
    return await sqlite_backend.delete_task_attempt_memories(research_id, task_id)

