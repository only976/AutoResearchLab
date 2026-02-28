"""Plan API - get, tree, run, stop, layout (execution graph)."""

import asyncio
import time

from fastapi import APIRouter, Query
from loguru import logger
from fastapi.responses import JSONResponse

from db import (
    get_effective_config,
    get_plan,
    list_plan_outputs,
    save_plan,
)
from visualization import build_layout_from_execution, compute_decomposition_layout
from plan_agent.index import run_plan

from ..schemas import PlanLayoutRequest, PlanRunRequest
from .. import state as api_state

router = APIRouter()


def _tree_update_payload(plan):
    """Build treeData + layout payload for plan-tree-update / plan-complete."""
    return {"treeData": plan["tasks"], "layout": compute_decomposition_layout(plan["tasks"])}


@router.post("/layout")
async def set_plan_layout(body: PlanLayoutRequest):
    """Set execution layout for plan execution graph."""
    execution = body.execution
    plan_id = body.plan_id
    layout = build_layout_from_execution(execution)
    try:
        api_state.runner.set_layout(layout, plan_id=plan_id, execution=execution)
    except ValueError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})
    return {"layout": layout}


@router.get("")
async def get_plan_route(plan_id: str = Query("test", alias="planId")):
    plan = await get_plan(plan_id)
    return {"plan": plan}


@router.get("/outputs")
async def get_plan_outputs(plan_id: str = Query("test", alias="planId")):
    """Load all task outputs for a plan. Used when restoring recent task."""
    outputs = await list_plan_outputs(plan_id)
    return {"outputs": outputs}


@router.get("/tree")
async def get_plan_tree(plan_id: str = Query("test", alias="planId")):
    plan = await get_plan(plan_id)
    if not plan or not plan.get("tasks") or len(plan["tasks"]) == 0:
        return {"treeData": [], "layout": None}
    return _tree_update_payload(plan)


@router.post("/stop")
async def stop_plan():
    """Stop plan: signal abort, cancel task."""
    state = api_state.plan_run_state
    if state and state.abort_event:
        state.abort_event.set()
    if state and state.run_task and not state.run_task.done():
        state.run_task.cancel()
    return {"success": True}


async def _run_plan_inner(body: PlanRunRequest):
    """Inner plan run logic. Runs in a cancellable task."""
    state = api_state.plan_run_state
    async with state.lock:
        if state.abort_event:
            state.abort_event.set()
        state.abort_event = asyncio.Event()
        state.abort_event.clear()
        abort_event = state.abort_event

    try:
        idea = body.idea
        if not idea or not isinstance(idea, str) or not idea.strip():
            raise ValueError("Idea is required for plan generation.")

        config = await get_effective_config()
        use_mock = config.get("useMock", True)

        plan_id = f"plan_{int(time.time() * 1000)}"
        plan = {
            "tasks": [{"task_id": "0", "description": idea.strip(), "dependencies": []}],
            "idea": idea.strip(),
        }
        await save_plan(plan, plan_id)

        await api_state.sio.emit("plan-start")

        if plan["tasks"]:
            await api_state.sio.emit("plan-tree-update", _tree_update_payload(plan))

        def on_tasks_batch(children, parent_task, all_tasks):
            if abort_event and abort_event.is_set():
                return
            plan["tasks"] = all_tasks
            if plan["tasks"]:
                asyncio.create_task(api_state.sio.emit("plan-tree-update", _tree_update_payload(plan)))

        def on_thinking(chunk, task_id=None, operation=None, schedule_info=None):
            if abort_event and abort_event.is_set():
                return
            payload = {"chunk": chunk}
            if task_id is not None:
                payload["taskId"] = task_id
            if operation is not None:
                payload["operation"] = operation
            if schedule_info is not None:
                payload["scheduleInfo"] = schedule_info
            asyncio.create_task(api_state.sio.emit("plan-thinking", payload))

        result = await run_plan(
            plan, None, on_thinking, abort_event, on_tasks_batch,
            use_mock=use_mock, api_config=config,
            skip_quality_assessment=body.skip_quality_assessment,
            plan_id=plan_id,
        )
        plan["tasks"] = result["tasks"]
        await save_plan(plan, plan_id)
        await api_state.sio.emit("plan-complete", {
            **_tree_update_payload(plan),
            "planId": plan_id,
            "qualityScore": plan.get("qualityScore"),
            "qualityComment": plan.get("qualityComment"),
        })
        return {"success": True, "planId": plan_id}
    finally:
        async with state.lock:
            if state.abort_event is abort_event:
                state.abort_event = None


@router.post("/run")
async def run_plan_route(body: PlanRunRequest):
    state = api_state.plan_run_state
    if state is None:
        return JSONResponse(status_code=503, content={"error": "API not initialized"})
    if state.run_task and not state.run_task.done():
        return JSONResponse(status_code=409, content={"error": "Plan run already in progress"})
    state.run_task = asyncio.create_task(_run_plan_inner(body))
    try:
        result = await state.run_task
        return result
    except asyncio.CancelledError:
        await api_state.sio.emit("plan-error", {"error": "Plan generation stopped by user"})
        return JSONResponse(status_code=499, content={"error": "Plan generation stopped by user"})
    except Exception as e:
        is_aborted = "Aborted" in str(e) or (e.__class__.__name__ == "CancelledError")
        err_msg = str(e)
        logger.warning("Plan run error: %s", err_msg)
        await api_state.sio.emit("plan-error", {"error": "Plan generation stopped by user" if is_aborted else err_msg})
        if "No decomposable task" in err_msg or "Idea is required" in err_msg or "Provide idea" in err_msg:
            return JSONResponse(status_code=400, content={"error": err_msg})
        return JSONResponse(status_code=500, content={"error": err_msg or "Failed to run plan"})
    finally:
        if state:
            state.run_task = None
