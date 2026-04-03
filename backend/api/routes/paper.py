"""Paper Agent API - 第四个 Agent，单轮 LLM 管道。与 idea/plan/task 统一：HTTP 仅触发，数据由 WebSocket 回传。"""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse
from loguru import logger
import os
import json
import re
from urllib.parse import quote

from db import get_effective_config, save_paper, get_execution
from paper_agent import run_paper_agent
from shared.realtime import build_thinking_emitter

from .. import state as api_state
from ..schemas import PaperRunRequest
from paper_agent.config import BASE_DIR

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

    try:
        await api_state.emit(session_id, "paper-start", {})

        execution = await get_execution(idea_id, plan_id)
        if not execution or not execution.get("runId"):
            raise ValueError("Execution runId not found. Run Task Agent first.")
        experiment_id = execution["runId"]

        result_payload = await run_paper_agent(
            experiment_id=experiment_id,
            api_config=config,
            on_thinking=on_thinking,
            abort_event=abort_event,
        )

        pdf_url = result_payload.get("pdf_url", "")
        content = result_payload.get("content", "")

        try:
            await save_paper(idea_id, plan_id, format_type=(format_type or "latex"), content=content)
        except Exception as e:
            logger.warning("Failed to persist paper: %s", e)

        await api_state.emit(session_id, "paper-complete", {
            "ideaId": idea_id,
            "planId": plan_id,
            "content": content,
            "format": format_type or "latex",
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

    idea_id = (body.idea_id or "").strip()
    plan_id = (body.plan_id or "").strip()
    if not idea_id or not plan_id:
        return JSONResponse(status_code=400, content={"error": "ideaId and planId are required"})

    format_type = (body.format or "latex").lower()

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

@router.get("/pdf/{experiment_id}")
async def serve_paper_pdf(experiment_id: str):
    """Serve the compiled PDF paper if it exists."""
    pdf_path = os.path.join(BASE_DIR, "output", experiment_id, "main.pdf")
    
    if os.path.exists(pdf_path):
        filename = f"Paper_{experiment_id[:8]}"
        
        # Try to read the title from outline.json
        outline_path = os.path.join(BASE_DIR, "output", experiment_id, "outline.json")
        if os.path.exists(outline_path):
            try:
                with open(outline_path, "r", encoding="utf-8") as f:
                    outline_data = json.load(f)
                    title = outline_data.get("title", "").strip()
                    if title:
                        # Replace problematic characters, keep alphanumeric, Chinese chars, spaces, and hyphens
                        safe_title = re.sub(r'[^\w\s\-\u4e00-\u9fa5]', '_', title)
                        # Replace multiple spaces with a single space, multiple underscores with a single underscore
                        safe_title = re.sub(r'\s+', ' ', safe_title)
                        safe_title = re.sub(r'_+', '_', safe_title).strip(' _')
                        if safe_title:
                            filename = safe_title
            except Exception as e:
                logger.warning(f"Failed to read outline for PDF filename: {e}")

        encoded_filename = quote(f"{filename}.pdf")
        return FileResponse(
            pdf_path, 
            media_type="application/pdf", 
            headers={"Content-Disposition": f"inline; filename*=utf-8''{encoded_filename}"} # Open in browser with correct filename
        )
        
    return JSONResponse(status_code=404, content={"error": "PDF not found."})
