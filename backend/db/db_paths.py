"""Path and sandbox helpers for DB/runtime filesystem operations."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from loguru import logger

DB_DIR = Path(__file__).parent
SANDBOX_DIR = Path(os.environ.get("MAARS_SANDBOX_DIR", str(DB_DIR.parent.parent / "sandbox"))).resolve()
DEFAULT_IDEA_ID = "test"
DEFAULT_PLAN_ID = "test"


def _validate_path_segment(value: str, name: str) -> None:
    """Reject empty or path-traversal values."""
    if not value or not isinstance(value, str):
        raise ValueError(f"{name} must be a non-empty string")
    if ".." in value or "/" in value or "\\" in value:
        raise ValueError(f"{name} must not contain path separators")


def _validate_idea_id(idea_id: str) -> None:
    _validate_path_segment(idea_id, "idea_id")


def _validate_plan_id(plan_id: str) -> None:
    _validate_path_segment(plan_id, "plan_id")


def _validate_task_id(task_id: str) -> None:
    """Reject path traversal and invalid task_id. Only alphanumeric and underscore."""
    _validate_path_segment(task_id, "task_id")
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
    """Return shared src dir. task_id is accepted for interface consistency but unused."""
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
