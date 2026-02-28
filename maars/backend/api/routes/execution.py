"""Execution API routes."""

import asyncio

from fastapi import APIRouter, Body, Query
from loguru import logger
from fastapi.responses import JSONResponse

from db import get_effective_config, get_execution, get_plan, save_execution
from task_agent.pools import get_stats
from plan_agent.execution_builder import build_execution_from_plan

from .. import state as api_state
from ..schemas import ExecutionRequest, ExecutionRetryRequest, ExecutionRunRequest

router = APIRouter()


@router.post("/generate-from-plan")
async def generate_from_plan(body: ExecutionRequest):
    """Extract atomic tasks from plan, resolve deps, save to execution.json."""
    plan_id = body.plan_id
    plan = await get_plan(plan_id)
    if not plan or not plan.get("tasks"):
        return JSONResponse(status_code=400, content={"error": "No plan found. Generate plan first."})
    execution = build_execution_from_plan(plan)
    await save_execution(execution, plan_id)
    return {"execution": execution}


@router.get("")
async def get_execution_route(plan_id: str = Query("test", alias="planId")):
    execution = await get_execution(plan_id)
    return {"execution": execution}


@router.get("/status")
async def get_execution_status(plan_id: str = Query(..., alias="planId")):
    """Return current execution state for plan. Used by frontend on WebSocket reconnect."""
    runner = api_state.runner
    if not runner.plan_id or runner.plan_id != plan_id:
        return {"running": False, "tasks": [], "stats": get_stats()}
    task_states = [{"task_id": t["task_id"], "status": t["status"]} for t in (runner.chain_cache or [])]
    return {
        "running": runner.is_running,
        "tasks": task_states,
        "stats": get_stats(),
    }


@router.post("/run")
async def run_execution(body: ExecutionRunRequest | None = Body(default=None)):
    """Start execution. Returns immediately; errors are pushed via WebSocket execution-error.
    If resumeFromTaskId is set, only that task and its downstream are reset and run (resume from task)."""
    runner = api_state.runner
    sio = api_state.sio

    # P0: Idempotency - reject if already running
    if runner.is_running:
        return JSONResponse(
            status_code=409,
            content={"error": "Execution is already running"},
        )

    # P1: plan_id consistency - validate if provided
    plan_id = body.plan_id if body else None
    if plan_id and runner.plan_id and runner.plan_id != plan_id:
        return JSONResponse(
            status_code=409,
            content={
                "error": f"Layout plan_id ({runner.plan_id}) does not match request planId ({plan_id})",
            },
        )

    config = await get_effective_config()
    resume_from_task_id = body.resume_from_task_id if body else None

    async def run():
        try:
            await runner.start_execution(
                api_config=config,
                resume_from_task_id=resume_from_task_id,
            )
        except Exception as e:
            logger.exception("Error in execution: {}", e)
            await sio.emit("execution-error", {"error": str(e)})

    asyncio.create_task(run())
    return {"success": True, "message": "Execution started"}


@router.post("/retry-task")
async def retry_task(body: ExecutionRetryRequest):
    """Retry a single failed task. If execution is running, retries in-place.
    If not running, starts execution from that task (resume from task)."""
    runner = api_state.runner
    sio = api_state.sio
    task_id = body.task_id

    if task_id not in (t.get("task_id") for t in (runner.chain_cache or [])):
        return JSONResponse(
            status_code=404,
            content={"error": f"Task {task_id} not found in execution map"},
        )

    if runner.is_running:
        ok = await runner.retry_task(task_id)
        if not ok:
            return JSONResponse(
                status_code=400,
                content={"error": f"Task {task_id} is not in failed state or cannot retry"},
            )
        return {"success": True, "message": "Task retry scheduled"}
    else:
        plan_id = body.plan_id or runner.plan_id
        if plan_id and runner.plan_id and runner.plan_id != plan_id:
            return JSONResponse(
                status_code=409,
                content={"error": "planId mismatch"},
            )
        config = await get_effective_config()

        async def run():
            try:
                await runner.start_execution(
                    api_config=config,
                    resume_from_task_id=task_id,
                )
            except Exception as e:
                logger.exception("Error in execution: {}", e)
                await sio.emit("execution-error", {"error": str(e)})

        asyncio.create_task(run())
        return {"success": True, "message": "Execution started from task"}
