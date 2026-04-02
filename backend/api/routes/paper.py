"""Paper Agent API - 第四个 Agent，单轮 LLM 管道。与 idea/plan/task 统一：HTTP 仅触发，数据由 WebSocket 回传。"""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger

from db import get_effective_config
from paper_agent import run_paper_agent
from shared.realtime import build_thinking_emitter

from .. import state as api_state
from ..schemas import PaperRunRequest
from paper_agent.config import BASE_DIR

router = APIRouter()

async def _run_paper_inner(session_id: str, state, experiment_id: str, abort_event=None):
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

    try:
        await api_state.emit(session_id, "paper-start", {})

        result_payload = await run_paper_agent(
            experiment_id=experiment_id,
            api_config=config,
            on_thinking=on_thinking,
            abort_event=abort_event,
        )

        pdf_url = result_payload.get("pdf_url", "")
        content = result_payload.get("content", "")

        await api_state.emit(session_id, "paper-complete", {
            "experimentId": experiment_id,
            "content": content,
            "format": "latex",
            "pdfUrl": pdf_url
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

    experiment_id = (body.experiment_id or "").strip()
    if not experiment_id:
        return JSONResponse(status_code=400, content={"error": "experimentId is required"})

    state.abort_event = asyncio.Event()
    state.run_task = asyncio.create_task(
        _run_paper_inner(session_id, state, experiment_id, abort_event=state.abort_event)
    )

    return {"success": True, "experimentId": experiment_id, "sessionId": session_id}


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

from fastapi.responses import FileResponse
import os

@router.get("/pdf/{experiment_id}")
async def serve_paper_pdf(experiment_id: str):
    """Serve the compiled PDF paper if it exists."""
    pdf_path = os.path.join(BASE_DIR, "output", experiment_id, "main.pdf")
    
    if os.path.exists(pdf_path):
        return FileResponse(
            pdf_path, 
            media_type="application/pdf", 
            filename=f"Paper_{experiment_id[:8]}.pdf",
            headers={"Content-Disposition": "inline"} # Open in browser
        )
        
    return JSONResponse(status_code=404, content={"error": "PDF not found."})
