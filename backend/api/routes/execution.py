"""Task Agent - Execution 阶段 API。Task Agent 含 Execution（执行）与 Validation（验证）两阶段，本模块为 Execution 阶段入口。"""

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
    """Task Agent Execution 阶段：从 Plan 提取原子任务、解析依赖，生成 execution.json。"""
    idea_id = body.idea_id or "test"
    plan_id = body.plan_id
    plan = await get_plan(idea_id, plan_id)
    if not plan or not plan.get("tasks"):
        return JSONResponse(status_code=400, content={"error": "No plan found. Generate plan first."})
    execution = build_execution_from_plan(plan)
    await save_execution(execution, idea_id, plan_id)
    return {"execution": execution}


@router.get("")
async def get_execution_route(idea_id: str = Query("test", alias="ideaId"), plan_id: str = Query("test", alias="planId")):
    """获取 Task Agent Execution 阶段数据（原子任务列表及状态）。"""
    execution = await get_execution(idea_id, plan_id)
    return {"execution": execution}


@router.get("/status")
async def get_execution_status(idea_id: str = Query(..., alias="ideaId"), plan_id: str = Query(..., alias="planId")):
    """Task Agent Execution 阶段当前状态。WebSocket 重连时前端用于同步。"""
    runner = api_state.runner
    if not runner.idea_id or runner.idea_id != idea_id or not runner.plan_id or runner.plan_id != plan_id:
        return {"running": False, "tasks": [], "stats": get_stats()}
    task_states = [{"task_id": t["task_id"], "status": t["status"]} for t in (runner.chain_cache or [])]
    return {
        "running": runner.is_running,
        "tasks": task_states,
        "stats": get_stats(),
    }


@router.post("/run")
async def run_execution(body: ExecutionRunRequest | None = Body(default=None)):
    """启动 Task Agent Execution 阶段。立即返回；错误由 WebSocket task-error 推送。
    resumeFromTaskId：仅重置该任务及下游，从该任务恢复执行。"""
    runner = api_state.runner
    sio = api_state.sio

    # P0: Idempotency - reject if already running
    if runner.is_running:
        return JSONResponse(
            status_code=409,
            content={"error": "Task Agent Execution is already running"},
        )

    # P1: idea_id + plan_id consistency - validate if provided
    idea_id = body.idea_id if body else None
    plan_id = body.plan_id if body else None
    if idea_id and runner.idea_id and runner.idea_id != idea_id:
        return JSONResponse(
            status_code=409,
            content={"error": f"Layout ideaId ({runner.idea_id}) does not match request ideaId ({idea_id})"},
        )
    if plan_id and runner.plan_id and runner.plan_id != plan_id:
        return JSONResponse(
            status_code=409,
            content={
                "error": f"Layout planId ({runner.plan_id}) does not match request planId ({plan_id})",
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
            await sio.emit("task-error", {"error": str(e)})

    asyncio.create_task(run())
    return {"success": True, "message": "Task Agent Execution started"}


@router.post("/stop")
async def stop_execution():
    """停止 Task Agent Execution 阶段：发送中止信号，取消任务，释放 worker。"""
    await api_state.runner.stop_async()
    return {"success": True}


@router.post("/retry-task")
async def retry_task(body: ExecutionRetryRequest):
    """Task Agent Execution 阶段：重试单个失败任务。运行中则原地重试；否则从该任务恢复执行。"""
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
        idea_id = body.idea_id or runner.idea_id
        plan_id = body.plan_id or runner.plan_id
        if idea_id and runner.idea_id and runner.idea_id != idea_id:
            return JSONResponse(status_code=409, content={"error": "ideaId mismatch"})
        if plan_id and runner.plan_id and runner.plan_id != plan_id:
            return JSONResponse(status_code=409, content={"error": "planId mismatch"})
        config = await get_effective_config()

        async def run():
            try:
                await runner.start_execution(
                    api_config=config,
                    resume_from_task_id=task_id,
                )
            except Exception as e:
                logger.exception("Error in execution: {}", e)
                await sio.emit("task-error", {"error": str(e)})

        asyncio.create_task(run())
        return {"success": True, "message": "Execution started from task"}
