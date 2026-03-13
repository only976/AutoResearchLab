"""Task Agent - Execution 阶段 API。Task Agent 含 Execution（执行）与 Validation（验证）两阶段，本模块为 Execution 阶段入口。"""

import asyncio

from fastapi import APIRouter, Body, Query, Request
from loguru import logger
from fastapi.responses import JSONResponse

from db import get_effective_config, get_execution, get_plan, save_execution
from task_agent.pools import get_stats
from plan_agent.execution_builder import build_execution_from_plan
from task_agent.docker_runtime import get_local_docker_status

from .. import state as api_state
from ..schemas import ExecutionRequest, ExecutionRetryRequest, ExecutionRunRequest

router = APIRouter()


def _start_execution_background(
    session_id: str,
    runner,
    config: dict,
    *,
    resume_from_task_id: str | None = None,
) -> None:
    async def run():
        try:
            await runner.start_execution(
                api_config=config,
                resume_from_task_id=resume_from_task_id,
                research_id=None,
            )
        except Exception as e:
            logger.exception("Error in execution: {}", e)
            await api_state.emit(session_id, "task-error", {"error": str(e)})

    asyncio.create_task(run())


@router.post("/generate-from-plan")
async def generate_from_plan(body: ExecutionRequest):
    """Task Agent Execution 阶段：从 Plan 提取原子任务、解析依赖，生成 execution.json。"""
    idea_id = (body.idea_id or "").strip()
    plan_id = (body.plan_id or "").strip()
    if not idea_id:
        return JSONResponse(status_code=400, content={"error": "ideaId is required before generating execution."})
    if not plan_id:
        return JSONResponse(status_code=400, content={"error": "planId is required before generating execution."})
    plan = await get_plan(idea_id, plan_id)
    if not plan or not plan.get("tasks"):
        return JSONResponse(status_code=400, content={"error": "No plan found. Generate plan first."})
    execution = build_execution_from_plan(plan)
    await save_execution(execution, idea_id, plan_id)
    return {"execution": execution}


@router.get("")
async def get_execution_route(idea_id: str = Query("test", alias="ideaId"), plan_id: str = Query("test", alias="planId")):
    """获取 Task Agent Execution 阶段数据（原子任务列表及状态）。"""
    if not (idea_id or "").strip() or not (plan_id or "").strip():
        return JSONResponse(status_code=400, content={"error": "ideaId and planId are required."})
    execution = await get_execution(idea_id, plan_id)
    return {"execution": execution}


@router.get("/status")
async def get_execution_status(request: Request, idea_id: str = Query(..., alias="ideaId"), plan_id: str = Query(..., alias="planId")):
    """Task Agent Execution 阶段当前状态。WebSocket 重连时前端用于同步。"""
    _, session = await api_state.require_session(request)
    runner = session.runner
    if not runner.idea_id or runner.idea_id != idea_id or not runner.plan_id or runner.plan_id != plan_id:
        return {"running": False, "tasks": [], "stats": get_stats()}
    task_states = [{"task_id": t["task_id"], "status": t["status"]} for t in (runner.chain_cache or [])]
    return {
        "running": runner.is_running,
        "tasks": task_states,
        "stats": get_stats(),
    }


@router.get("/runtime-status")
async def get_execution_runtime_status(request: Request, idea_id: str | None = Query(default=None, alias="ideaId"), plan_id: str | None = Query(default=None, alias="planId")):
    """Return local Docker connectivity and current execution runtime status for the session."""
    _, session = await api_state.require_session(request)
    runner = session.runner
    enabled = bool((runner.api_config or {}).get("taskAgentMode"))
    status = await get_local_docker_status(enabled=enabled, container_name=runner.docker_container_name or None)
    runner_runtime = runner.docker_runtime_status if isinstance(getattr(runner, "docker_runtime_status", None), dict) else {}
    for key in ("image", "taskId", "srcDir", "stepDir", "sandboxRoot", "error"):
        value = runner_runtime.get(key)
        if value not in (None, ""):
            status[key] = value
    if runner.execution_run_id:
        status["executionRunId"] = runner.execution_run_id
    if runner.idea_id:
        status["ideaId"] = runner.idea_id
    if runner.plan_id:
        status["planId"] = runner.plan_id
    status["running"] = bool(runner.is_running)
    if idea_id and runner.idea_id and idea_id != runner.idea_id:
        status["running"] = False
    if plan_id and runner.plan_id and plan_id != runner.plan_id:
        status["running"] = False
    return status


@router.post("/run")
async def run_execution(request: Request, body: ExecutionRunRequest | None = Body(default=None)):
    """启动 Task Agent Execution 阶段。立即返回；错误由 WebSocket task-error 推送。
    resumeFromTaskId：仅重置该任务及下游，从该任务恢复执行。"""
    session_id, session = await api_state.require_session(request)
    runner = session.runner

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
    _start_execution_background(
        session_id,
        runner,
        config,
        resume_from_task_id=resume_from_task_id,
    )
    return {"success": True, "message": "Task Agent Execution started", "sessionId": session_id}


@router.post("/stop")
async def stop_execution(request: Request):
    """停止 Task Agent Execution 阶段：发送中止信号，取消任务，释放 worker。"""
    _, session = await api_state.require_session(request)
    await session.runner.stop_async()
    return {"success": True}


@router.post("/retry-task")
async def retry_task(request: Request, body: ExecutionRetryRequest):
    """Task Agent Execution 阶段：重试单个失败任务。运行中则原地重试；否则从该任务恢复执行。"""
    session_id, session = await api_state.require_session(request)
    runner = session.runner
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
        _start_execution_background(
            session_id,
            runner,
            config,
            resume_from_task_id=task_id,
        )
        return {"success": True, "message": "Execution started from task", "sessionId": session_id}
