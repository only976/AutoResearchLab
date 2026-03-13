"""Idea Agent API - 文献收集（Refine）。三个 Agent 之一，与 Plan/Task 统一：HTTP 仅触发，数据由 WebSocket 回传。"""

import asyncio
import time

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from loguru import logger

from db import get_effective_config, get_idea, save_idea
from idea_agent import collect_literature, run_idea_agent
from shared.reflection import reflection_loop
from shared.realtime import build_thinking_emitter

from .. import state as api_state
from ..schemas import IdeaCollectRequest

router = APIRouter()


@router.get("")
async def get_idea_route(idea_id: str = Query("test", alias="ideaId")):
    """Get idea data (idea text, keywords, papers, etc.)."""
    idea_data = await get_idea(idea_id)
    return {"idea": idea_data}


async def _run_collect_inner(session_id: str, state, idea_id: str, idea: str, limit: int, abort_event=None):
    """后台执行文献收集，通过 WebSocket 回传数据。"""
    config = await get_effective_config()
    logger.info(
        "Idea run start session_id={} idea_id={} chars={} limit={} mode={}",
        session_id,
        idea_id,
        len((idea or "").strip()),
        limit,
        "agent" if config.get("ideaAgentMode") else ("mock" if config.get("ideaUseMock") else "llm"),
    )
    on_thinking = build_thinking_emitter(
        api_state.sio,
        event_name="idea-thinking",
        source="idea",
        default_operation="Refine",
        room=session_id,
        warning_label="idea-thinking",
    )
    try:
        await api_state.emit(session_id, "idea-start", {})
        if config.get("ideaAgentMode"):
            result = await run_idea_agent(
                idea=idea,
                api_config=config,
                limit=limit,
                on_thinking=on_thinking,
                abort_event=abort_event,
            )
        else:
            result = await collect_literature(
                idea=idea,
                api_config=config,
                limit=limit,
                on_thinking=on_thinking,
                abort_event=abort_event,
            )

        async def _rerun_idea():
            if config.get("ideaAgentMode"):
                return await run_idea_agent(
                    idea=idea, api_config=config, limit=limit,
                    on_thinking=on_thinking, abort_event=abort_event,
                )
            return await collect_literature(
                idea=idea, api_config=config, limit=limit,
                on_thinking=on_thinking, abort_event=abort_event,
            )

        reflected = await reflection_loop(
            agent_type="idea",
            run_fn=_rerun_idea,
            initial_output=result,
            context={"idea": idea},
            on_thinking=on_thinking,
            abort_event=abort_event,
            api_config=config,
        )
        result = reflected["output"]
        reflection_data = reflected.get("reflection")
        logger.info(
            "Idea run result idea_id={} keywords={} papers={} refined_chars={} reflection_iterations={}",
            idea_id,
            len(result.get("keywords", []) or []),
            len(result.get("papers", []) or []),
            len((result.get("refined_idea") or "").strip()),
            (reflection_data or {}).get("iterations", 0),
        )

        idea_data = {
            "idea": idea,
            "keywords": result.get("keywords", []),
            "papers": result.get("papers", []),
            "refined_idea": result.get("refined_idea"),
        }
        await save_idea(idea_data, idea_id)
        complete_payload = {
            "ideaId": idea_id,
            "keywords": result.get("keywords", []),
            "papers": result.get("papers", []),
            "refined_idea": result.get("refined_idea"),
        }
        if reflection_data:
            complete_payload["reflection"] = {
                "iterations": reflection_data.get("iterations", 0),
                "bestScore": reflection_data.get("best_score", 0),
                "skillsCreated": [s["name"] for s in reflection_data.get("skills_created", [])],
            }
        await api_state.emit(session_id, "idea-complete", complete_payload)
        logger.info("Idea run complete session_id={} idea_id={}", session_id, idea_id)
    except asyncio.CancelledError:
        logger.warning("Idea run cancelled session_id={} idea_id={}", session_id, idea_id)
        await api_state.emit_safe(
            session_id,
            "idea-error",
            {"error": "Idea Agent stopped by user", "ideaId": idea_id},
            warning_label="idea-error emit (cancel)",
        )
        raise
    except Exception as e:
        logger.exception("Idea Agent error session_id={} idea_id={}", session_id, idea_id)
        await api_state.emit_safe(
            session_id,
            "idea-error",
            {"error": str(e), "ideaId": idea_id},
            warning_label="idea-error emit",
        )
        raise
    finally:
        api_state.clear_run_state(state)


@router.post("/collect")
async def collect_literature_route(body: IdeaCollectRequest, request: Request):
    """Collect arXiv literature from fuzzy idea. 立即返回，数据由 WebSocket idea-complete 回传。"""
    session_id, session = await api_state.require_session(request)
    state = session.idea_run_state
    if state.run_task and not state.run_task.done():
        return JSONResponse(status_code=409, content={"error": "Idea Agent already in progress"})

    idea_id = f"idea_{int(time.time() * 1000)}"
    idea = (body.idea or "").strip()
    await save_idea({"idea": idea, "keywords": [], "papers": []}, idea_id)

    if not idea:
        return JSONResponse(status_code=400, content={"error": "idea is required", "ideaId": idea_id})

    state.abort_event = asyncio.Event()
    state.run_task = asyncio.create_task(
        _run_collect_inner(session_id, state, idea_id, idea, body.limit or 10, abort_event=state.abort_event)
    )

    return {"success": True, "ideaId": idea_id, "sessionId": session_id}


@router.post("/stop")
async def stop_idea(request: Request):
    """停止 Idea Agent：发送中止信号，取消任务，立即推送 idea-error。"""
    session_id, session = await api_state.require_session(request)
    await api_state.stop_run_state(
        session_id,
        session.idea_run_state,
        error_event="idea-error",
        error_message="Idea Agent stopped by user",
    )
    return {"success": True}
