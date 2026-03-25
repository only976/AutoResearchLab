"""Task artifact / AI response validation wrappers around sqlite_backend_artifacts."""

from __future__ import annotations

import asyncio
from collections import OrderedDict

from .db_paths import _validate_idea_id, _validate_plan_id, _validate_task_id
from .sqlite_backend_artifacts import (
    delete_task_artifact as _sb_delete_task_artifact,
    get_ai_responses as _sb_get_ai_responses,
    get_task_artifact as _sb_get_task_artifact,
    list_plan_outputs as _sb_list_plan_outputs,
    save_ai_responses_blob as _sb_save_ai_responses_blob,
    save_task_artifact as _sb_save_task_artifact,
    save_validation_report as _sb_save_validation_report,
)


async def get_task_artifact(idea_id: str, plan_id: str, task_id: str):
    """Read task artifact. Returns dict or None."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    _validate_task_id(task_id)
    return await _sb_get_task_artifact(idea_id, plan_id, task_id)


async def list_plan_outputs(idea_id: str, plan_id: str) -> dict:
    """Load all task outputs for a plan. Returns {task_id: output_dict}."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return await _sb_list_plan_outputs(idea_id, plan_id)


async def save_task_artifact(idea_id: str, plan_id: str, task_id: str, value) -> dict:
    """Write task artifact."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    _validate_task_id(task_id)
    return await _sb_save_task_artifact(idea_id, plan_id, task_id, value)


async def delete_task_artifact(idea_id: str, plan_id: str, task_id: str) -> bool:
    """Remove task artifact. Returns True if deleted."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    _validate_task_id(task_id)
    return await _sb_delete_task_artifact(idea_id, plan_id, task_id)


async def save_validation_report(idea_id: str, plan_id: str, task_id: str, report: dict) -> dict:
    """Save task validation report."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    _validate_task_id(task_id)
    return await _sb_save_validation_report(idea_id, plan_id, task_id, report)


# --- AI response persistence (atomicity, decompose, format) ---

_MAX_LOCKS = 256
_ai_save_locks: OrderedDict[tuple, asyncio.Lock] = OrderedDict()


def _get_ai_save_lock(idea_id: str, plan_id: str, response_type: str) -> asyncio.Lock:
    key = (idea_id, plan_id, response_type)
    if key in _ai_save_locks:
        _ai_save_locks.move_to_end(key)
        return _ai_save_locks[key]
    lock = asyncio.Lock()
    _ai_save_locks[key] = lock
    while len(_ai_save_locks) > _MAX_LOCKS:
        _ai_save_locks.popitem(last=False)
    return lock


async def get_ai_responses(idea_id: str, plan_id: str, response_type: str) -> dict:
    """Read AI responses for a plan. response_type: atomicity, decompose, format."""
    if response_type not in ("atomicity", "decompose", "format"):
        return {}
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return await _sb_get_ai_responses(idea_id, plan_id, response_type)


async def save_ai_response(idea_id: str, plan_id: str, response_type: str, key: str, entry: dict) -> None:
    """Incrementally save one AI response. entry = {content: ..., reasoning: ...}."""
    if response_type not in ("atomicity", "decompose", "format"):
        return
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    lock = _get_ai_save_lock(idea_id, plan_id, response_type)
    async with lock:
        data = await get_ai_responses(idea_id, plan_id, response_type)
        data[key] = entry
        await _sb_save_ai_responses_blob(idea_id, plan_id, response_type, data)
