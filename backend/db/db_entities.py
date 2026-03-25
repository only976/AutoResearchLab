"""Idea / Plan / Execution validation wrappers around sqlite_backend_entities."""

from __future__ import annotations

from .db_paths import _validate_idea_id, _validate_plan_id
from .sqlite_backend_entities import (
    get_execution as _sb_get_execution,
    get_idea as _sb_get_idea,
    get_plan as _sb_get_plan,
    list_idea_ids as _sb_list_idea_ids,
    list_plan_ids as _sb_list_plan_ids,
    list_recent_plans as _sb_list_recent_plans,
    save_execution as _sb_save_execution,
    save_idea as _sb_save_idea,
    save_plan as _sb_save_plan,
)


async def get_idea(idea_id: str):
    """Get idea (Refine output: idea, keywords, papers, etc.)."""
    _validate_idea_id(idea_id)
    return await _sb_get_idea(idea_id)


async def save_idea(idea_data: dict, idea_id: str) -> dict:
    """Save idea."""
    _validate_idea_id(idea_id)
    return await _sb_save_idea(idea_id, idea_data)


async def list_idea_ids() -> list:
    """List idea IDs, sorted by updated_at (newest first)."""
    return await _sb_list_idea_ids()


async def get_plan(idea_id: str, plan_id: str):
    """Get plan (tasks only, no idea)."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return await _sb_get_plan(idea_id, plan_id)


async def save_plan(plan: dict, idea_id: str, plan_id: str) -> dict:
    """Save plan."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return await _sb_save_plan(idea_id, plan_id, plan)


async def list_plan_ids(idea_id: str) -> list:
    """List plan IDs under an idea, sorted by updated_at (newest first)."""
    _validate_idea_id(idea_id)
    return await _sb_list_plan_ids(idea_id)


async def list_recent_plans() -> list:
    """List (ideaId, planId) pairs, sorted by updated_at (newest first)."""
    return await _sb_list_recent_plans()


async def get_execution(idea_id: str, plan_id: str):
    """Get execution."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return await _sb_get_execution(idea_id, plan_id)


async def save_execution(execution: dict, idea_id: str, plan_id: str) -> dict:
    """Save execution."""
    _validate_idea_id(idea_id)
    _validate_plan_id(plan_id)
    return await _sb_save_execution(idea_id, plan_id, execution)
