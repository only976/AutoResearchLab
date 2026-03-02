"""Idea Agent API - 文献收集（Refine）。三个 Agent 之一，与 Plan/Task 统一：HTTP 仅触发，数据由 WebSocket 回传。"""

import asyncio
import time

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from loguru import logger

from db import get_effective_config, get_idea, save_idea
from idea_agent import collect_literature, run_idea_agent
from shared.reflection import reflection_loop

from .. import state as api_state
from ..schemas import IdeaCollectRequest

router = APIRouter()


@router.get("")
async def get_idea_route(idea_id: str = Query("test", alias="ideaId")):
    """Get idea data (idea text, keywords, papers, etc.)."""
    idea_data = await get_idea(idea_id)
    return {"idea": idea_data}


def _make_on_thinking(sio):
    """构造 on_thinking 回调，通过 WebSocket 推送 idea-thinking 事件。
    与 Task Agent 对齐：使用 await emit 保证顺序与送达。
    签名与 Plan/Task 统一：(chunk, task_id, operation, schedule_info)
    """

    async def on_thinking(
        chunk: str,
        task_id=None,
        operation=None,
        schedule_info=None,
    ):
        if not chunk and schedule_info is None:
            return
        if not sio:
            return
        payload = {
            "chunk": chunk or "",
            "source": "idea",
            "taskId": task_id,
            "operation": operation or "Refine",
        }
        if schedule_info is not None:
            payload["scheduleInfo"] = schedule_info
        try:
            await sio.emit("idea-thinking", payload)
        except Exception as e:
            logger.warning("idea-thinking emit failed: %s", e)

    return on_thinking


async def _run_collect_inner(idea_id: str, idea: str, limit: int, abort_event=None):
    """后台执行文献收集，通过 WebSocket 回传数据。"""
    config = await get_effective_config()
    sio = getattr(api_state, "sio", None)
    on_thinking = _make_on_thinking(sio) if sio else None
    try:
        if sio:
            await sio.emit("idea-start", {})
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

        idea_data = {
            "idea": idea,
            "keywords": result.get("keywords", []),
            "papers": result.get("papers", []),
            "refined_idea": result.get("refined_idea"),
        }
        await save_idea(idea_data, idea_id)
        if sio:
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
            await sio.emit("idea-complete", complete_payload)
    except asyncio.CancelledError:
        try:
            if sio:
                await sio.emit("idea-error", {"error": "Idea Agent stopped by user", "ideaId": idea_id})
        except Exception as emit_err:
            logger.warning("idea-error emit (cancel) failed: %s", emit_err)
        raise
    except Exception as e:
        logger.warning("Idea Agent error: %s", e)
        try:
            if sio:
                await sio.emit("idea-error", {"error": str(e), "ideaId": idea_id})
        except Exception as emit_err:
            logger.warning("idea-error emit failed: %s", emit_err)
        raise
    finally:
        state = getattr(api_state, "idea_run_state", None)
        if state:
            state.run_task = None
            state.abort_event = None


@router.post("/collect")
async def collect_literature_route(body: IdeaCollectRequest):
    """Collect arXiv literature from fuzzy idea. 立即返回，数据由 WebSocket idea-complete 回传。"""
    state = getattr(api_state, "idea_run_state", None)
    if state and state.run_task and not state.run_task.done():
        return JSONResponse(status_code=409, content={"error": "Idea Agent already in progress"})

    idea_id = f"idea_{int(time.time() * 1000)}"
    idea = (body.idea or "").strip()
    await save_idea({"idea": idea, "keywords": [], "papers": []}, idea_id)

    if not idea:
        return JSONResponse(status_code=400, content={"error": "idea is required", "ideaId": idea_id})

    state = getattr(api_state, "idea_run_state", None)
    if state:
        state.abort_event = asyncio.Event()
        state.abort_event.clear()
        state.run_task = asyncio.create_task(
            _run_collect_inner(idea_id, idea, body.limit or 10, abort_event=state.abort_event)
        )

    return {"success": True, "ideaId": idea_id}


@router.post("/stop")
async def stop_idea():
    """停止 Idea Agent：发送中止信号，取消任务，立即推送 idea-error。"""
    state = getattr(api_state, "idea_run_state", None)
    if state and state.abort_event:
        state.abort_event.set()
    if state and state.run_task and not state.run_task.done():
        state.run_task.cancel()
        try:
            sio = getattr(api_state, "sio", None)
            if sio:
                await sio.emit("idea-error", {"error": "Idea Agent stopped by user"})
        except Exception as e:
            logger.warning("idea-error emit (stop) failed: %s", e)
    return {"success": True}
