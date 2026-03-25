"""Research and paper related DB operations with filesystem cleanup helpers."""

from __future__ import annotations

import shutil

from loguru import logger

from .db_paths import (
    _get_idea_dir,
    _validate_idea_id,
    _validate_plan_id,
    _validate_task_id,
    find_execution_run_ids_for_research,
    remove_execution_sandbox_root,
)
from .sqlite_backend_research import (
    create_research as _sb_create_research,
    clear_research_stage_data_for_retry as _sb_clear_research_stage_data_for_retry,
    delete_research_cascade as _sb_delete_research_cascade,
    get_paper as _sb_get_paper,
    get_research as _sb_get_research,
    list_researches as _sb_list_researches,
    save_paper as _sb_save_paper,
    update_research_stage as _sb_update_research_stage,
)
from .sqlite_backend_memory import (
    delete_task_attempt_memories as _sb_delete_task_attempt_memories,
    list_task_attempt_memories as _sb_list_task_attempt_memories,
    save_task_attempt_memory as _sb_save_task_attempt_memory,
)


async def create_research(research_id: str, prompt: str, title: str) -> None:
    return await _sb_create_research(research_id, prompt, title)


async def list_researches() -> list[dict]:
    return await _sb_list_researches()


async def get_research(research_id: str) -> dict | None:
    return await _sb_get_research(research_id)


async def update_research_stage(
    research_id: str,
    *,
    stage: str | None = None,
    stage_status: str | None = None,
    current_idea_id: str | None = None,
    current_plan_id: str | None = None,
    error: str | None = None,
) -> None:
    return await _sb_update_research_stage(
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
    return await _sb_save_paper(idea_id, plan_id, format_type=format_type, content=content)


async def get_paper(idea_id: str, plan_id: str) -> dict | None:
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return await _sb_get_paper(idea_id, plan_id)


async def clear_research_stage_data_for_retry(idea_id: str | None, plan_id: str | None, stage: str) -> dict:
    """Clear current-stage and downstream data for retry; also removes matching execution sandbox runs."""
    idea = str(idea_id or "").strip()
    plan = str(plan_id or "").strip()
    result = await _sb_clear_research_stage_data_for_retry(idea, plan, stage)
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
    result = await _sb_delete_research_cascade(research_id)

    if not result.get("success"):
        return result

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
    return await _sb_save_task_attempt_memory(research_id, task_id, attempt, value)


async def list_task_attempt_memories(research_id: str, task_id: str | None = None) -> list[dict]:
    if not research_id or not isinstance(research_id, str):
        raise ValueError("research_id must be a non-empty string")
    if task_id:
        _validate_task_id(task_id)
    return await _sb_list_task_attempt_memories(research_id, task_id)


async def delete_task_attempt_memories(research_id: str, task_id: str | None = None) -> int:
    if not research_id or not isinstance(research_id, str):
        raise ValueError("research_id must be a non-empty string")
    if task_id:
        _validate_task_id(task_id)
    return await _sb_delete_task_attempt_memories(research_id, task_id)
