"""Research API - Product-level unit (Research) that runs the full pipeline.

Research is the primary unit of work. It links to the latest ideaId and planId
created during the pipeline runs.

Pipeline stages: refine -> plan -> execute -> paper
"""

import asyncio
import time
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger

from db import (
    clear_research_stage_data_for_retry,
    create_research,
    delete_research_cascade,
    get_effective_config,
    get_execution,
    get_idea,
    get_paper,
    get_plan,
    get_research,
    list_plan_outputs,
    list_researches,
    save_execution,
    save_idea,
    update_research_stage,
)
from plan_agent.execution_builder import build_execution_from_plan
from visualization import build_layout_from_execution

from .. import state as api_state
from ..schemas import PlanRunRequest, ResearchCreateRequest, ResearchRunRequest

# Reuse existing stage runners
from .idea import _run_collect_inner
from .plan import _run_plan_inner
from .paper import _run_paper_inner

router = APIRouter()


_RUNNING: dict[tuple[str, str], dict] = {}


def _stage_rank(stage: str) -> int:
    order = {"refine": 0, "plan": 1, "execute": 2, "paper": 3}
    return order.get((stage or "").strip().lower(), 0)


def _normalize_stage(stage: str) -> str:
    s = (stage or "").strip().lower()
    return s if s in ("refine", "plan", "execute", "paper") else "refine"


def _completed_rank(research: dict | None) -> int:
    r = research or {}
    stage = _normalize_stage(str(r.get("stage") or "refine"))
    status = str(r.get("stageStatus") or "idle").strip().lower()
    rank = _stage_rank(stage)
    if status == "completed":
        return rank
    return rank - 1


def _check_stage_prerequisites(research: dict | None, target_stage: str) -> str | None:
    """Return error message if target stage cannot start because predecessors are not completed."""
    stage = _normalize_stage(target_stage)
    target_rank = _stage_rank(stage)
    if target_rank <= 0:
        return None

    completed = _completed_rank(research)
    required = target_rank - 1
    if completed < required:
        order = ["refine", "plan", "execute", "paper"]
        need_stage = order[required]
        cur_stage = _normalize_stage(str((research or {}).get("stage") or "refine"))
        cur_status = str((research or {}).get("stageStatus") or "idle").strip().lower() or "idle"
        return f"Cannot start '{stage}' before '{need_stage}' is completed (current: {cur_stage} · {cur_status})."
    return None


def _make_research_id() -> str:
    return f"research_{int(time.time() * 1000)}"


def _make_title(prompt: str) -> str:
    s = (prompt or "").strip().replace("\n", " ")
    s = " ".join(s.split())
    if not s:
        return "Untitled"
    return s[:64]


@router.get("")
async def list_researches_route(request: Request):
    await api_state.require_session(request)
    items = await list_researches()
    return {"items": items}


@router.post("")
async def create_research_route(body: ResearchCreateRequest, request: Request):
    await api_state.require_session(request)
    prompt = (body.prompt or "").strip()
    if not prompt:
        return JSONResponse(status_code=400, content={"error": "prompt is required"})
    research_id = _make_research_id()
    await create_research(research_id, prompt, _make_title(prompt))
    return {"researchId": research_id}


@router.get("/{research_id}")
async def get_research_route(research_id: str, request: Request):
    await api_state.require_session(request)
    research = await get_research(research_id)
    if not research:
        return JSONResponse(status_code=404, content={"error": "Research not found"})
    idea_id = research.get("currentIdeaId")
    plan_id = research.get("currentPlanId")

    idea = await get_idea(idea_id) if idea_id else None
    plan = await get_plan(idea_id, plan_id) if (idea_id and plan_id) else None
    execution = await get_execution(idea_id, plan_id) if (idea_id and plan_id) else None
    outputs = await list_plan_outputs(idea_id, plan_id) if (idea_id and plan_id) else {}
    paper = await get_paper(idea_id, plan_id) if (idea_id and plan_id) else None

    return {
        "research": research,
        "idea": idea,
        "plan": plan,
        "execution": execution,
        "outputs": outputs,
        "paper": paper,
    }


@router.delete("/{research_id}")
async def delete_research_route(research_id: str, request: Request):
    await api_state.require_session(request)
    research = await get_research(research_id)
    if not research:
        return JSONResponse(status_code=404, content={"error": "Research not found"})

    # stop in-memory runner if this research is running in current process
    for (sid, rid), entry in list(_RUNNING.items()):
        if rid != research_id:
            continue
        session = api_state.sessions.get(sid)
        runner = getattr(session, "runner", None) if session else None
        if runner and getattr(runner, "is_running", False):
            try:
                await runner.stop_async()
            except Exception:
                logger.exception("Failed to stop runner during research deletion research_id={} session_id={}", research_id, sid)
        task = entry.get("task")
        if task and not task.done():
            task.cancel()
        _RUNNING.pop((sid, rid), None)

    await delete_research_cascade(research_id)
    return {"success": True, "researchId": research_id}


def _next_stage(stage: str) -> str | None:
    order = ["refine", "plan", "execute", "paper"]
    s = _normalize_stage(stage)
    idx = order.index(s)
    if idx + 1 >= len(order):
        return None
    return order[idx + 1]


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
    await update_research_stage(research_id, stage="refine", stage_status="completed", current_idea_id=idea_id)
    await _emit_stage(session_id, research_id, "refine", "completed")
    return idea_id, None


async def _run_stage_plan(session_id: str, session, research_id: str, idea_id: str, plan_id: str) -> str:
    await _emit_stage(session_id, research_id, "plan", "running")
    await update_research_stage(research_id, stage="plan", stage_status="running", current_plan_id=plan_id, error=None)
    await _run_plan_inner(PlanRunRequest(skip_quality_assessment=False), idea_id, plan_id, session_id, session.plan_run_state)
    plan = await get_plan(idea_id, plan_id)
    if not plan or not plan.get("tasks"):
        raise ValueError("Plan not found or empty after planning")
    await update_research_stage(research_id, stage="plan", stage_status="completed", current_plan_id=plan_id)
    await _emit_stage(session_id, research_id, "plan", "completed")
    return plan_id


async def _run_stage_execute(session_id: str, session, research_id: str, idea_id: str, plan_id: str) -> None:
    plan = await get_plan(idea_id, plan_id)
    if not plan or not plan.get("tasks"):
        raise ValueError("Plan not found or empty after planning")
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


@router.post("/{research_id}/run")
async def run_research_route(research_id: str, body: ResearchRunRequest, request: Request):
    session_id, session = await api_state.require_session(request)
    research = await get_research(research_id)
    if not research:
        return JSONResponse(status_code=404, content={"error": "Research not found"})
    if _is_session_busy(session_id):
        return JSONResponse(status_code=409, content={"error": "Another research pipeline is already running in this session"})

    paper_format = (body.format or "markdown").lower().strip()
    if paper_format not in ("markdown", "latex"):
        paper_format = "markdown"

    await clear_research_stage_data_for_retry(
        research.get("currentIdeaId"),
        research.get("currentPlanId"),
        "refine",
    )

    _start_stage_pipeline_task(
        session_id=session_id,
        session=session,
        research_id=research_id,
        start_stage="refine",
        paper_format=paper_format,
        reset_start_stage=True,
    )
    return {
        "success": True,
        "researchId": research_id,
        "sessionId": session_id,
        "mode": "run",
        "startStage": "refine",
        "autoChain": True,
    }


@router.post("/{research_id}/stop")
async def stop_research_route(research_id: str, request: Request):
    """Stop current research pipeline run in this session (pause).

    Semantics: cancel the pipeline task + set abort signals so downstream agents return quickly.
    """

    session_id, session = await api_state.require_session(request)

    research = await get_research(research_id)
    if not research:
        return JSONResponse(status_code=404, content={"error": "Research not found"})

    key = (session_id, research_id)
    task = _running_task_for(session_id, research_id)
    await _abort_stage_runners(session, include_execute=True)

    if task and not task.done():
        task.cancel()
        await update_research_stage(research_id, stage_status="stopped", error=None)
        try:
            stage = _normalize_stage(research.get("stage") or "refine")
            await _emit_stage(session_id, research_id, stage, "stopped")
        except Exception:
            pass
        return {"success": True, "researchId": research_id, "sessionId": session_id, "stopped": True}

    return {"success": True, "researchId": research_id, "sessionId": session_id, "stopped": False, "message": "No running pipeline"}


@router.post("/{research_id}/retry")
async def retry_research_route(research_id: str, body: ResearchRunRequest, request: Request):
    """Retry research pipeline starting from the current stage, using existing upstream artifacts."""

    session_id, session = await api_state.require_session(request)

    research = await get_research(research_id)
    if not research:
        return JSONResponse(status_code=404, content={"error": "Research not found"})

    if _is_session_busy(session_id):
        return JSONResponse(status_code=409, content={"error": "Another research pipeline is already running in this session"})

    paper_format = (body.format or "markdown").lower().strip()
    if paper_format not in ("markdown", "latex"):
        paper_format = "markdown"

    start_stage = _normalize_stage(research.get("stage") or "refine")
    await clear_research_stage_data_for_retry(
        research.get("currentIdeaId"),
        research.get("currentPlanId"),
        start_stage,
    )
    _start_stage_pipeline_task(
        session_id=session_id,
        session=session,
        research_id=research_id,
        start_stage=start_stage,
        paper_format=paper_format,
        reset_start_stage=True,
    )
    return {"success": True, "researchId": research_id, "sessionId": session_id, "mode": "retry", "startStage": start_stage, "autoChain": True}


@router.post("/{research_id}/stage/{stage}/run")
async def run_research_stage_route(research_id: str, stage: str, body: ResearchRunRequest, request: Request):
    session_id, session = await api_state.require_session(request)
    stage = _normalize_stage(stage)
    research = await get_research(research_id)
    if not research:
        return JSONResponse(status_code=404, content={"error": "Research not found"})
    prereq_err = _check_stage_prerequisites(research, stage)
    if prereq_err:
        return JSONResponse(status_code=400, content={"error": prereq_err})
    if _is_session_busy(session_id):
        return JSONResponse(status_code=409, content={"error": "Another research pipeline is already running in this session"})
    paper_format = (body.format or "markdown").lower().strip()
    if paper_format not in ("markdown", "latex"):
        paper_format = "markdown"
    _start_stage_pipeline_task(
        session_id=session_id,
        session=session,
        research_id=research_id,
        start_stage=stage,
        paper_format=paper_format,
        reset_start_stage=True,
    )
    return {"success": True, "researchId": research_id, "sessionId": session_id, "mode": "run-stage", "startStage": stage, "autoChain": True}


@router.post("/{research_id}/stage/{stage}/resume")
async def resume_research_stage_route(research_id: str, stage: str, body: ResearchRunRequest, request: Request):
    session_id, session = await api_state.require_session(request)
    stage = _normalize_stage(stage)
    research = await get_research(research_id)
    if not research:
        return JSONResponse(status_code=404, content={"error": "Research not found"})
    prereq_err = _check_stage_prerequisites(research, stage)
    if prereq_err:
        return JSONResponse(status_code=400, content={"error": prereq_err})
    current_stage = _normalize_stage(research.get("stage") or "refine")
    current_status = str(research.get("stageStatus") or "idle").strip().lower()
    if current_stage != stage or current_status not in ("stopped", "failed"):
        return JSONResponse(
            status_code=409,
            content={
                "error": (
                    f"Resume only applies to the same stage in stopped/failed state "
                    f"(current: {current_stage} · {current_status})."
                )
            },
        )
    if _is_session_busy(session_id):
        return JSONResponse(status_code=409, content={"error": "Another research pipeline is already running in this session"})
    paper_format = (body.format or "markdown").lower().strip()
    if paper_format not in ("markdown", "latex"):
        paper_format = "markdown"
    _start_stage_pipeline_task(
        session_id=session_id,
        session=session,
        research_id=research_id,
        start_stage=stage,
        paper_format=paper_format,
        reset_start_stage=False,
    )
    return {"success": True, "researchId": research_id, "sessionId": session_id, "mode": "resume-stage", "startStage": stage, "autoChain": True}


@router.post("/{research_id}/stage/{stage}/retry")
async def retry_research_stage_route(research_id: str, stage: str, body: ResearchRunRequest, request: Request):
    session_id, session = await api_state.require_session(request)
    stage = _normalize_stage(stage)
    research = await get_research(research_id)
    if not research:
        return JSONResponse(status_code=404, content={"error": "Research not found"})
    prereq_err = _check_stage_prerequisites(research, stage)
    if prereq_err:
        return JSONResponse(status_code=400, content={"error": prereq_err})
    if _is_session_busy(session_id):
        return JSONResponse(status_code=409, content={"error": "Another research pipeline is already running in this session"})
    paper_format = (body.format or "markdown").lower().strip()
    if paper_format not in ("markdown", "latex"):
        paper_format = "markdown"
    await clear_research_stage_data_for_retry(
        research.get("currentIdeaId"),
        research.get("currentPlanId"),
        stage,
    )
    _start_stage_pipeline_task(
        session_id=session_id,
        session=session,
        research_id=research_id,
        start_stage=stage,
        paper_format=paper_format,
        reset_start_stage=True,
    )
    return {"success": True, "researchId": research_id, "sessionId": session_id, "mode": "retry-stage", "startStage": stage, "autoChain": True}


@router.post("/{research_id}/stage/{stage}/stop")
async def stop_research_stage_route(research_id: str, stage: str, request: Request):
    session_id, session = await api_state.require_session(request)
    stage = _normalize_stage(stage)
    research = await get_research(research_id)
    if not research:
        return JSONResponse(status_code=404, content={"error": "Research not found"})
    entry = _RUNNING.get((session_id, research_id)) or {}
    running_stage = _normalize_stage(entry.get("stage") or (research.get("stage") or "refine"))
    task = entry.get("task")
    await _abort_stage_runners(session, include_execute=True)
    if task and not task.done() and running_stage == stage:
        task.cancel()
        await update_research_stage(research_id, stage=stage, stage_status="stopped", error=None)
        await _emit_stage(session_id, research_id, stage, "stopped")
        return {"success": True, "researchId": research_id, "sessionId": session_id, "stage": stage, "stopped": True}
    return {"success": True, "researchId": research_id, "sessionId": session_id, "stage": stage, "stopped": False, "message": "No running stage task"}
