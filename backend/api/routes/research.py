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
    create_research,
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


_RUNNING: dict[tuple[str, str], asyncio.Task] = {}


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


@router.post("/{research_id}/run")
async def run_research_route(research_id: str, body: ResearchRunRequest, request: Request):
    session_id, session = await api_state.require_session(request)

    research = await get_research(research_id)
    if not research:
        return JSONResponse(status_code=404, content={"error": "Research not found"})

    # Single pipeline per session (shared runner/run-states)
    for (sid, _rid), t in list(_RUNNING.items()):
        if sid == session_id and t and not t.done():
            return JSONResponse(status_code=409, content={"error": "Another research pipeline is already running in this session"})

    key = (session_id, research_id)

    paper_format = (body.format or "markdown").lower().strip()
    if paper_format not in ("markdown", "latex"):
        paper_format = "markdown"

    async def _pipeline():
        try:
            await api_state.emit_safe(session_id, "research-stage", {"researchId": research_id, "stage": "refine", "status": "running"})
            await update_research_stage(research_id, stage="refine", stage_status="running", error=None)

            prompt = (research.get("prompt") or "").strip()
            idea_id = f"idea_{int(time.time() * 1000)}"
            await update_research_stage(research_id, current_idea_id=idea_id, current_plan_id=None)
            await save_idea({"idea": prompt, "keywords": [], "papers": []}, idea_id)

            # Refine
            session.idea_run_state.abort_event = asyncio.Event()
            await _run_collect_inner(
                session_id,
                session.idea_run_state,
                idea_id,
                prompt,
                limit=10,
                abort_event=session.idea_run_state.abort_event,
            )

            # Plan
            await api_state.emit_safe(session_id, "research-stage", {"researchId": research_id, "stage": "plan", "status": "running"})
            await update_research_stage(research_id, stage="plan", stage_status="running")
            plan_id = f"plan_{int(time.time() * 1000)}"
            await update_research_stage(research_id, current_plan_id=plan_id)
            await _run_plan_inner(PlanRunRequest(skip_quality_assessment=False), idea_id, plan_id, session_id, session.plan_run_state)

            plan = await get_plan(idea_id, plan_id)
            if not plan or not plan.get("tasks"):
                raise ValueError("Plan not found or empty after planning")

            # Execute
            await api_state.emit_safe(session_id, "research-stage", {"researchId": research_id, "stage": "execute", "status": "running"})
            await update_research_stage(research_id, stage="execute", stage_status="running")
            execution = build_execution_from_plan(plan)
            await save_execution(execution, idea_id, plan_id)
            layout = build_layout_from_execution(execution)
            session.runner.set_layout(layout, idea_id=idea_id, plan_id=plan_id, execution=execution)

            config = await get_effective_config()
            await session.runner.start_execution(api_config=config)

            # Paper
            await api_state.emit_safe(session_id, "research-stage", {"researchId": research_id, "stage": "paper", "status": "running"})
            await update_research_stage(research_id, stage="paper", stage_status="running")
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
            await api_state.emit_safe(session_id, "research-stage", {"researchId": research_id, "stage": "paper", "status": "completed"})
        except asyncio.CancelledError:
            await update_research_stage(research_id, stage_status="failed", error="Research pipeline cancelled")
            raise
        except Exception as e:
            logger.exception("Research pipeline failed")
            await update_research_stage(research_id, stage_status="failed", error=str(e))
            try:
                await api_state.emit_safe(session_id, "research-stage", {"researchId": research_id, "stage": "error", "status": "failed", "error": str(e)})
            except Exception:
                pass
            try:
                await api_state.emit_safe(session_id, "research-error", {"researchId": research_id, "error": str(e)})
            except Exception:
                pass
        finally:
            _RUNNING.pop(key, None)

    task = asyncio.create_task(_pipeline())
    _RUNNING[key] = task
    return {"success": True, "researchId": research_id, "sessionId": session_id}
