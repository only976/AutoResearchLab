"""Plan Agent API - 任务分解（Plan）。三个 Agent 之一，与 Idea/Task 统一：HTTP 仅触发，数据由 WebSocket 回传。"""

import asyncio
import time

from fastapi import APIRouter, Query, Request
from loguru import logger
from fastapi.responses import JSONResponse

from db import (
    DEFAULT_IDEA_ID,
    get_effective_config,
    get_idea,
    get_plan,
    list_plan_outputs,
    save_plan,
)
from shared.idea_utils import get_idea_text
from visualization import build_layout_from_execution, compute_decomposition_layout
from plan_agent.index import run_plan
from shared.reflection import reflection_loop
from shared.realtime import build_thinking_emitter

from ..schemas import PlanLayoutRequest, PlanRunRequest
from .. import state as api_state

router = APIRouter()


def _tree_update_payload(plan):
    """Build treeData + layout payload for plan-tree-update / plan-complete."""
    return {"treeData": plan["tasks"], "layout": compute_decomposition_layout(plan["tasks"])}


@router.post("/layout")
async def set_plan_layout(body: PlanLayoutRequest, request: Request):
    """设置 Task Agent Execution 阶段的可视化布局（execution graph）。"""
    _, session = await api_state.require_session(request)
    execution = body.execution
    idea_id = body.idea_id or DEFAULT_IDEA_ID
    plan_id = body.plan_id
    layout = build_layout_from_execution(execution)
    try:
        session.runner.set_layout(layout, idea_id=idea_id, plan_id=plan_id, execution=execution)
    except ValueError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})
    return {"layout": layout}


@router.get("")
async def get_plan_route(idea_id: str = Query("test", alias="ideaId"), plan_id: str = Query("test", alias="planId")):
    plan = await get_plan(idea_id, plan_id)
    return {"plan": plan}


@router.get("/outputs")
async def get_plan_outputs(idea_id: str = Query("test", alias="ideaId"), plan_id: str = Query("test", alias="planId")):
    """Load all task outputs for a plan. Used when restoring recent task."""
    outputs = await list_plan_outputs(idea_id, plan_id)
    return {"outputs": outputs}


@router.get("/tree")
async def get_plan_tree(idea_id: str = Query("test", alias="ideaId"), plan_id: str = Query("test", alias="planId")):
    plan = await get_plan(idea_id, plan_id)
    if not plan or not plan.get("tasks") or len(plan["tasks"]) == 0:
        return {"treeData": [], "layout": None}
    return _tree_update_payload(plan)


@router.post("/stop")
async def stop_plan(request: Request):
    """停止 Plan Agent：发送中止信号，取消任务，立即推送 plan-error 以便前端恢复 UI。"""
    session_id, session = await api_state.require_session(request)
    await api_state.stop_run_state(
        session_id,
        session.plan_run_state,
        error_event="plan-error",
        error_message="Plan Agent stopped by user",
        emit_when_idle=True,
    )
    return {"success": True}


async def _run_plan_inner(body: PlanRunRequest, idea_id: str, plan_id: str, session_id: str, state):
    """后台执行 plan 生成，通过 WebSocket 回传数据。与 idea/task 统一：HTTP 仅触发。"""
    async with state.lock:
        if state.abort_event:
            state.abort_event.set()
        state.abort_event = asyncio.Event()
        abort_event = state.abort_event

    try:
        idea_data = await get_idea(idea_id)
        if not idea_data or not idea_data.get("idea"):
            raise ValueError("Idea not found. Please Refine first to create an idea.")
        raw_idea = idea_data["idea"].strip() if isinstance(idea_data.get("idea"), str) else ""
        refined = idea_data.get("refined_idea")
        idea = get_idea_text(refined) or raw_idea

        config = await get_effective_config()
        use_mock = config.get("planUseMock", True)

        plan = {
            "tasks": [{"task_id": "0", "description": idea, "dependencies": []}],
            "idea": idea,
        }
        await save_plan(plan, idea_id, plan_id)

        await api_state.emit(session_id, "plan-start", {})

        if plan["tasks"]:
            await api_state.emit(session_id, "plan-tree-update", _tree_update_payload(plan))

        def on_tasks_batch(children, parent_task, all_tasks):
            if abort_event and abort_event.is_set():
                return
            plan["tasks"] = all_tasks
            if plan["tasks"]:
                api_state.emit_background(session_id, "plan-tree-update", _tree_update_payload(plan))

        _on_thinking_emit = build_thinking_emitter(
            api_state.sio,
            event_name="plan-thinking",
            source="plan",
            default_operation="Decompose",
            room=session_id,
            warning_label="plan-thinking",
        )

        async def on_thinking(chunk, task_id=None, operation=None, schedule_info=None):
            if abort_event and abort_event.is_set():
                return
            await _on_thinking_emit(chunk, task_id, operation, schedule_info)

        result = await run_plan(
            plan, None, on_thinking, abort_event, on_tasks_batch,
            use_mock=use_mock, api_config=config,
            skip_quality_assessment=body.skip_quality_assessment,
            idea_id=idea_id,
            plan_id=plan_id,
        )
        plan["tasks"] = result["tasks"]

        async def _rerun_plan():
            rerun_plan = {
                "tasks": [{"task_id": "0", "description": idea, "dependencies": []}],
                "idea": idea,
            }
            r = await run_plan(
                rerun_plan, None, on_thinking, abort_event, on_tasks_batch,
                use_mock=use_mock, api_config=config,
                skip_quality_assessment=True,
                idea_id=idea_id, plan_id=plan_id,
            )
            plan["tasks"] = r["tasks"]
            plan.pop("qualityScore", None)
            plan.pop("qualityComment", None)
            return {"tasks": r["tasks"]}

        reflected = await reflection_loop(
            agent_type="plan",
            run_fn=_rerun_plan,
            initial_output={"tasks": plan["tasks"]},
            context={"idea": idea},
            on_thinking=on_thinking,
            abort_event=abort_event,
            api_config=config,
        )
        plan["tasks"] = reflected["output"]["tasks"]
        reflection_data = reflected.get("reflection")

        plan_to_save = {"tasks": plan["tasks"], "qualityScore": plan.get("qualityScore"), "qualityComment": plan.get("qualityComment")}
        await save_plan(plan_to_save, idea_id, plan_id)

        complete_payload = {
            **_tree_update_payload(plan),
            "ideaId": idea_id,
            "planId": plan_id,
            "qualityScore": plan.get("qualityScore"),
            "qualityComment": plan.get("qualityComment"),
        }
        if reflection_data:
            complete_payload["reflection"] = {
                "iterations": reflection_data.get("iterations", 0),
                "bestScore": reflection_data.get("best_score", 0),
                "skillsCreated": [s["name"] for s in reflection_data.get("skills_created", [])],
            }
        await api_state.emit(session_id, "plan-complete", complete_payload)
    except asyncio.CancelledError:
        await api_state.emit_safe(
            session_id,
            "plan-error",
            {"error": "Plan Agent stopped by user"},
            warning_label="plan-error emit (cancel)",
        )
        raise
    except Exception as e:
        err_msg = str(e)
        logger.warning("Plan run error: %s", err_msg)
        await api_state.emit_safe(
            session_id,
            "plan-error",
            {"error": "Plan Agent stopped by user" if "Aborted" in err_msg else err_msg},
            warning_label="plan-error emit",
        )
        raise
    finally:
        async with state.lock:
            if state.abort_event is abort_event:
                state.abort_event = None
        state.run_task = None


@router.post("/run")
async def run_plan_route(body: PlanRunRequest, request: Request):
    """立即返回，数据由 WebSocket plan-complete 回传。与 idea/task 统一。"""
    session_id, session = await api_state.require_session(request)
    state = session.plan_run_state
    if state.run_task and not state.run_task.done():
        return JSONResponse(status_code=409, content={"error": "Plan run already in progress"})

    idea_id = (body.idea_id or "").strip() or None
    if not idea_id or idea_id == DEFAULT_IDEA_ID or not idea_id.startswith("idea_"):
        return JSONResponse(status_code=400, content={"error": "Please Refine first to create an idea. Idea ID is required for plan generation."})

    idea_data = await get_idea(idea_id)
    if not idea_data or not idea_data.get("idea"):
        return JSONResponse(status_code=400, content={"error": "Idea not found. Please Refine first to create an idea."})

    plan_id = f"plan_{int(time.time() * 1000)}"
    state.run_task = asyncio.create_task(_run_plan_inner(body, idea_id, plan_id, session_id, state))

    return {"success": True, "ideaId": idea_id, "planId": plan_id, "sessionId": session_id}
