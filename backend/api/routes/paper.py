"""Paper Agent API - 第四个 Agent，单轮 LLM 管道。与 idea/plan/task 统一：HTTP 仅触发，数据由 WebSocket 回传。"""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger

from db import get_effective_config, get_plan, list_plan_outputs, save_paper
from paper_agent import run_paper_agent
from shared.realtime import build_thinking_emitter

from .. import state as api_state
from ..schemas import PaperRunRequest

router = APIRouter()

async def _run_paper_inner(session_id: str, state, idea_id: str, plan_id: str, format_type: str, abort_event=None):
    """后台执行论文生成，通过 WebSocket 回传数据。"""
    config = await get_effective_config()
    on_thinking = build_thinking_emitter(
        api_state.sio,
        event_name="paper-thinking",
        source="paper",
        default_operation="Paper",
        room=session_id,
        warning_label="paper-thinking",
    )

    plan = await get_plan(idea_id, plan_id)
    if not plan or not plan.get("tasks"):
        await api_state.emit_safe(
            session_id,
            "paper-error",
            {"error": "Plan not found or empty."},
            warning_label="paper-error emit",
        )
        return

    outputs = await list_plan_outputs(idea_id, plan_id)

    try:
        await api_state.emit(session_id, "paper-start", {})

        content = await run_paper_agent(
            plan=plan,
            outputs=outputs,
            api_config=config,
            format_type=format_type or "markdown",
            on_thinking=on_thinking,
            abort_event=abort_event,
        )

        try:
            await save_paper(idea_id, plan_id, format_type=(format_type or "markdown"), content=content)
        except Exception as e:
            logger.warning("Failed to persist paper: %s", e)

        await api_state.emit(session_id, "paper-complete", {
            "ideaId": idea_id,
            "planId": plan_id,
            "content": content,
            "format": format_type or "markdown",
        })
    except asyncio.CancelledError:
        await api_state.emit_safe(
            session_id,
            "paper-error",
            {"error": "Paper Agent stopped by user"},
            warning_label="paper-error emit (cancel)",
        )
        raise
    except Exception as e:
        logger.warning("Paper Agent error: %s", e)
        await api_state.emit_safe(
            session_id,
            "paper-error",
            {"error": str(e)},
            warning_label="paper-error emit",
        )
        raise
    finally:
        api_state.clear_run_state(state)


@router.post("/run")
async def run_paper_route(body: PaperRunRequest, request: Request):
    """Generate paper draft. 立即返回，数据由 WebSocket paper-complete 回传。"""
    session_id, session = await api_state.require_session(request)
    state = session.paper_run_state
    if state.run_task and not state.run_task.done():
        return JSONResponse(status_code=409, content={"error": "Paper Agent already in progress"})

    idea_id = (body.idea_id or "").strip()
    plan_id = (body.plan_id or "").strip()
    if not idea_id or not plan_id:
        return JSONResponse(status_code=400, content={"error": "ideaId and planId are required"})

    plan = await get_plan(idea_id, plan_id)
    if not plan or not plan.get("tasks"):
        return JSONResponse(status_code=400, content={"error": "Plan not found. Generate plan first."})

    format_type = (body.format or "markdown").lower()
    if format_type not in ("markdown", "latex"):
        format_type = "markdown"

    state.abort_event = asyncio.Event()
    state.run_task = asyncio.create_task(
        _run_paper_inner(session_id, state, idea_id, plan_id, format_type, abort_event=state.abort_event)
    )

    return {"success": True, "ideaId": idea_id, "planId": plan_id, "sessionId": session_id}


@router.post("/stop")
async def stop_paper(request: Request):
    """停止 Paper Agent。"""
    session_id, session = await api_state.require_session(request)
    await api_state.stop_run_state(
        session_id,
        session.paper_run_state,
        error_event="paper-error",
        error_message="Paper Agent stopped by user",
    )
    return {"success": True}
