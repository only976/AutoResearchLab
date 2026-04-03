"""Pipeline runtime helpers for research routes."""

import asyncio
import time

from loguru import logger

from db import get_effective_config, get_plan, get_research, save_execution, save_idea, update_research_stage
from plan_agent.execution_builder import build_execution_from_plan
from visualization import build_layout_from_execution

from .. import state as api_state
from ..schemas import PlanRunRequest
from .idea import _run_collect_inner
from .paper import _run_paper_inner
from .plan import _run_plan_inner
from .research_helpers import (
    _normalize_stage,
    _validate_execute_completion,
    _validate_paper_completion,
    _validate_plan_completion,
    _validate_refine_completion,
)

_RUNNING: dict[tuple[str, str], dict] = {}


async def _emit_stage(session_id: str, research_id: str, stage: str, status: str, error: str | None = None) -> None:
    payload = {"researchId": research_id, "stage": stage, "status": status}
    if error:
        payload["error"] = error
    await api_state.emit_safe(session_id, "research-stage", payload)


def _running_task_for(session_id: str, research_id: str) -> asyncio.Task | None:
    entry = _RUNNING.get((session_id, research_id)) or {}
    return entry.get("task")


def _is_session_busy(session_id: str) -> bool:
    for (sid, _rid), entry in list(_RUNNING.items()):
        task = entry.get("task") if isinstance(entry, dict) else None
        if sid == session_id and task and not task.done():
            return True
    return False


async def _abort_stage_runners(session, include_execute: bool = True) -> None:
    try:
        if getattr(session.idea_run_state, "abort_event", None):
            session.idea_run_state.abort_event.set()
    except Exception:
        pass
    try:
        if getattr(session.plan_run_state, "abort_event", None):
            session.plan_run_state.abort_event.set()
    except Exception:
        pass
    if include_execute:
        try:
            await session.runner.stop_async()
        except Exception:
            pass
    try:
        if getattr(session.paper_run_state, "abort_event", None):
            session.paper_run_state.abort_event.set()
    except Exception:
        pass


async def _cancel_research_running_tasks(research_id: str, sessions: dict) -> None:
    """Stop and unregister all in-process pipeline tasks for a research id."""

    for (sid, rid), entry in list(_RUNNING.items()):
        if rid != research_id:
            continue
        session = sessions.get(sid)
        runner = getattr(session, "runner", None) if session else None
        if runner and getattr(runner, "is_running", False):
            try:
                await runner.stop_async()
            except Exception:
                logger.exception(
                    "Failed to stop runner during research deletion research_id={} session_id={}",
                    research_id,
                    sid,
                )
        task = entry.get("task")
        if task and not task.done():
            task.cancel()
        _RUNNING.pop((sid, rid), None)


async def _run_stage_refine(session_id: str, session, research_id: str, prompt: str, idea_id: str) -> tuple[str, str | None]:
    await _emit_stage(session_id, research_id, "refine", "running")
    await update_research_stage(research_id, stage="refine", stage_status="running", current_idea_id=idea_id, current_plan_id=None, error=None)
    await save_idea({"idea": prompt, "keywords": [], "papers": []}, idea_id)
    session.idea_run_state.abort_event = asyncio.Event()
    await _run_collect_inner(
        session_id,
        session.idea_run_state,
        idea_id,
        prompt,
        limit=10,
        abort_event=session.idea_run_state.abort_event,
    )
    refine_ok, refine_err = await _validate_refine_completion(idea_id)
    if not refine_ok:
        raise ValueError(f"Refine finished without required artifacts: {refine_err}")
    await update_research_stage(research_id, stage="refine", stage_status="completed", current_idea_id=idea_id)
    await _emit_stage(session_id, research_id, "refine", "completed")
    return idea_id, None


async def _run_stage_plan(session_id: str, session, research_id: str, idea_id: str, plan_id: str) -> str:
    await _emit_stage(session_id, research_id, "plan", "running")
    await update_research_stage(research_id, stage="plan", stage_status="running", current_plan_id=plan_id, error=None)
    await _run_plan_inner(PlanRunRequest(skip_quality_assessment=False), idea_id, plan_id, session_id, session.plan_run_state)
    plan_ok, plan_err = await _validate_plan_completion(idea_id, plan_id)
    if not plan_ok:
        raise ValueError(f"Plan finished without required artifacts: {plan_err}")
    await update_research_stage(research_id, stage="plan", stage_status="completed", current_plan_id=plan_id)
    await _emit_stage(session_id, research_id, "plan", "completed")
    return plan_id


async def _run_stage_execute(session_id: str, session, research_id: str, idea_id: str, plan_id: str) -> None:
    plan_ok, plan_err = await _validate_plan_completion(idea_id, plan_id)
    if not plan_ok:
        raise ValueError(f"Plan prerequisite is invalid: {plan_err}")
    plan = await get_plan(idea_id, plan_id)
    await _emit_stage(session_id, research_id, "execute", "running")
    await update_research_stage(research_id, stage="execute", stage_status="running", error=None)
    execution = build_execution_from_plan(plan)
    if not execution.get("tasks"):
        raise ValueError("No atomic tasks found in current plan. Execution is blocked until Plan produces executable atomic tasks.")
    await save_execution(execution, idea_id, plan_id)
    layout = build_layout_from_execution(execution)
    session.runner.set_layout(layout, idea_id=idea_id, plan_id=plan_id, execution=execution)
    config = await get_effective_config()
    await session.runner.start_execution(api_config=config, research_id=research_id)
    execute_ok, execute_err = await _validate_execute_completion(idea_id, plan_id)
    if not execute_ok:
        raise ValueError(f"Execute finished without required artifacts: {execute_err}")
    await update_research_stage(research_id, stage="execute", stage_status="completed")
    await _emit_stage(session_id, research_id, "execute", "completed")


async def _run_stage_paper(session_id: str, session, research_id: str, idea_id: str, plan_id: str, paper_format: str) -> None:
    await _emit_stage(session_id, research_id, "paper", "running")
    await update_research_stage(research_id, stage="paper", stage_status="running", error=None)
    session.paper_run_state.abort_event = asyncio.Event()
    
    await _run_paper_inner(
        session_id,
        session.paper_run_state,
        idea_id,
        plan_id,
        paper_format,
        abort_event=session.paper_run_state.abort_event,
    )
    paper_ok, paper_err = await _validate_paper_completion(idea_id, plan_id)
    if not paper_ok:
        raise ValueError(f"Paper finished without required artifacts: {paper_err}")
    await update_research_stage(research_id, stage="paper", stage_status="completed")
    await _emit_stage(session_id, research_id, "paper", "completed")


async def _run_stage_chain(
    *,
    session_id: str,
    session,
    research_id: str,
    start_stage: str,
    paper_format: str,
    reset_start_stage: bool,
) -> None:
    key = (session_id, research_id)
    start_stage = _normalize_stage(start_stage)
    try:
        research_live = await get_research(research_id)
        if not research_live:
            raise ValueError("Research not found")

        prompt = (research_live.get("prompt") or "").strip()
        idea_id = (research_live.get("currentIdeaId") or "").strip() or None
        plan_id = (research_live.get("currentPlanId") or "").strip() or None

        if start_stage == "refine":
            if _RUNNING.get(key):
                _RUNNING[key]["stage"] = "refine"
            if reset_start_stage or not idea_id:
                idea_id = f"idea_{int(time.time() * 1000)}"
            idea_id, _ = await _run_stage_refine(session_id, session, research_id, prompt, idea_id)
            start_stage = "plan"

        if start_stage == "plan":
            if _RUNNING.get(key):
                _RUNNING[key]["stage"] = "plan"
            if not idea_id:
                raise ValueError("Idea not found. Please run Refine first.")
            if reset_start_stage or not plan_id:
                plan_id = f"plan_{int(time.time() * 1000)}"
            plan_id = await _run_stage_plan(session_id, session, research_id, idea_id, plan_id)
            start_stage = "execute"

        if start_stage == "execute":
            if _RUNNING.get(key):
                _RUNNING[key]["stage"] = "execute"
            if not idea_id or not plan_id:
                raise ValueError("Plan not found. Please run Plan first.")
            await _run_stage_execute(session_id, session, research_id, idea_id, plan_id)
            start_stage = "paper"

        if start_stage == "paper":
            if _RUNNING.get(key):
                _RUNNING[key]["stage"] = "paper"
            if not idea_id or not plan_id:
                raise ValueError("Plan not found. Please run Plan first.")
            await _run_stage_paper(session_id, session, research_id, idea_id, plan_id, paper_format)

    except asyncio.CancelledError:
        logger.warning("Research pipeline cancelled research_id={} session_id={}", research_id, session_id)
        research_live = await get_research(research_id)
        stage = _normalize_stage((research_live or {}).get("stage") or "refine")
        await update_research_stage(research_id, stage_status="stopped", error="Research pipeline stopped by user")
        await _emit_stage(session_id, research_id, stage, "stopped")
        raise
    except Exception as e:
        logger.exception("Research pipeline failed research_id={} session_id={}", research_id, session_id)
        research_live = await get_research(research_id)
        stage = _normalize_stage((research_live or {}).get("stage") or start_stage)
        await update_research_stage(research_id, stage=stage, stage_status="failed", error=str(e))
        await _emit_stage(session_id, research_id, stage, "failed", str(e))
        await api_state.emit_safe(session_id, "research-error", {"researchId": research_id, "error": str(e)})
    finally:
        _RUNNING.pop(key, None)


def _start_stage_pipeline_task(
    *,
    session_id: str,
    session,
    research_id: str,
    start_stage: str,
    paper_format: str,
    reset_start_stage: bool,
) -> None:
    key = (session_id, research_id)

    async def _run():
        await _run_stage_chain(
            session_id=session_id,
            session=session,
            research_id=research_id,
            start_stage=start_stage,
            paper_format=paper_format,
            reset_start_stage=reset_start_stage,
        )

    task = asyncio.create_task(_run())
    _RUNNING[key] = {"task": task, "stage": _normalize_stage(start_stage)}
