import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from backend.maars_integration import ensure_maars_path
from backend.schemas.request_models import (
    ExperimentCreateRequest,
    ExperimentPlanRequest,
    ExperimentRunRequest,
    FeedbackRequest,
)

router = APIRouter(prefix="/api/experiments")


def _idea_to_text(payload: ExperimentPlanRequest | ExperimentCreateRequest) -> str:
    idea = payload.idea or {}
    topic = getattr(payload, "topic", None) or {}
    for field in ("title", "name", "summary", "description"):
        if isinstance(idea, dict) and idea.get(field):
            return str(idea[field])
    for field in ("title", "name", "summary", "description"):
        if isinstance(topic, dict) and topic.get(field):
            return str(topic[field])
    if isinstance(idea, dict):
        return json.dumps(idea, ensure_ascii=True)
    return str(idea) if idea else "Untitled idea"


def _load_maars():
    ensure_maars_path()
    from api import state as maars_state
    from db import (
        get_effective_config,
        get_execution,
        get_plan,
        get_task_artifact,
        list_plan_ids,
        list_plan_outputs,
        save_execution,
        save_plan,
    )
    from plan_agent.execution_builder import build_execution_from_plan
    from plan_agent.index import run_plan
    from visualization import build_layout_from_execution

    return {
        "state": maars_state,
        "get_effective_config": get_effective_config,
        "get_execution": get_execution,
        "get_plan": get_plan,
        "get_task_artifact": get_task_artifact,
        "list_plan_ids": list_plan_ids,
        "list_plan_outputs": list_plan_outputs,
        "save_execution": save_execution,
        "save_plan": save_plan,
        "build_execution_from_plan": build_execution_from_plan,
        "build_layout_from_execution": build_layout_from_execution,
        "run_plan": run_plan,
    }


@router.get("")
async def get_experiments() -> List[Dict[str, Any]]:
    maars = _load_maars()
    plan_ids = await maars["list_plan_ids"]()
    items: List[Dict[str, Any]] = []
    for plan_id in plan_ids:
        plan = await maars["get_plan"](plan_id)
        title = plan.get("idea") if isinstance(plan, dict) else None
        if not title and isinstance(plan, dict):
            tasks = plan.get("tasks") or []
            if tasks:
                title = tasks[0].get("description")
        items.append(
            {
                "id": plan_id,
                "title": title or plan_id,
                "status": "initialized",
                "updated_at": None,
                "created_at": None,
            }
        )
    return items


@router.get("/{exp_id}/meta")
async def get_experiment_meta(exp_id: str) -> Dict[str, Any]:
    maars = _load_maars()
    plan = await maars["get_plan"](exp_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Meta not found")
    idea = plan.get("idea") if isinstance(plan, dict) else None
    return {
        "id": exp_id,
        "plan_id": exp_id,
        "idea": {"title": idea or exp_id},
        "topic": {},
    }


@router.get("/{exp_id}/plan")
async def get_experiment_plan(exp_id: str) -> Dict[str, Any]:
    maars = _load_maars()
    plan = await maars["get_plan"](exp_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.get("/{exp_id}/conclusion")
async def get_experiment_conclusion(exp_id: str) -> Dict[str, Any]:
    raise HTTPException(status_code=404, detail="Conclusion not found")


@router.post("")
async def create_experiment(payload: ExperimentCreateRequest) -> Dict[str, Any]:
    plan_id = f"plan_{int(time.time() * 1000)}"
    return {"id": plan_id}


@router.post("/{exp_id}/plan")
async def generate_plan(exp_id: str, payload: ExperimentPlanRequest) -> Dict[str, Any]:
    maars = _load_maars()
    config = await maars["get_effective_config"]()
    idea_text = _idea_to_text(payload)
    plan = {
        "tasks": [{"task_id": "0", "description": idea_text, "dependencies": []}],
        "idea": idea_text,
    }
    result = await maars["run_plan"](
        plan,
        None,
        lambda *args, **kwargs: None,
        abort_event=None,
        on_tasks_batch=None,
        use_mock=config.get("useMock", True),
        api_config=config,
        skip_quality_assessment=False,
        plan_id=exp_id,
    )
    plan["tasks"] = result.get("tasks", plan.get("tasks"))
    await maars["save_plan"](plan, exp_id)
    return plan


@router.post("/{exp_id}/run")
async def run_experiment(exp_id: str, payload: ExperimentRunRequest) -> Dict[str, Any]:
    maars = _load_maars()
    plan = await maars["get_plan"](exp_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    execution = maars["build_execution_from_plan"](plan)
    await maars["save_execution"](execution, exp_id)
    layout = maars["build_layout_from_execution"](execution)

    state = maars["state"]
    runner = state.runner
    if runner is None:
        raise HTTPException(status_code=503, detail="MAARS runner not initialized")

    try:
        runner.set_layout(layout, plan_id=exp_id, execution=execution)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    config = await maars["get_effective_config"]()

    async def _run() -> None:
        await runner.start_execution(api_config=config, resume_from_task_id=None)

    asyncio.create_task(_run())
    return {"status": "started", "plan_id": exp_id}


@router.get("/{exp_id}/status")
async def get_status(exp_id: str) -> Dict[str, Any]:
    maars = _load_maars()
    state = maars["state"]
    runner = state.runner

    execution = await maars["get_execution"](exp_id)
    tasks = (execution or {}).get("tasks") or []
    total_steps = len(tasks)
    done_steps = sum(1 for t in tasks if t.get("status") == "done")
    failed_steps = sum(1 for t in tasks if t.get("status") in {"execution-failed", "validation-failed"})

    is_running = bool(runner and runner.is_running and runner.plan_id == exp_id)
    if is_running:
        status = "running"
        details = "Execution in progress"
    elif total_steps == 0:
        status = "initialized"
        details = "Waiting for execution to start..."
    elif failed_steps > 0:
        status = "failed"
        details = f"{failed_steps} tasks failed"
    elif done_steps == total_steps:
        status = "completed"
        details = "All tasks completed"
    else:
        status = "paused"
        details = "Execution ready"

    return {
        "experiment_status": status,
        "current_step": done_steps,
        "total_steps": total_steps,
        "step_name": "Execution",
        "details": details,
    }


@router.get("/{exp_id}/logs")
async def get_logs(exp_id: str, lines: int = Query(default=200, ge=1, le=2000)) -> Dict[str, Any]:
    return {"lines": []}


@router.get("/{exp_id}/artifacts")
async def get_artifacts(exp_id: str) -> Dict[str, Any]:
    maars = _load_maars()
    outputs = await maars["list_plan_outputs"](exp_id)
    manifest = []
    for task_id, output in outputs.items():
        manifest.append(
            {
                "name": f"task_{task_id}.json",
                "type": "json",
                "stage": "execution",
                "step_id": task_id,
                "summary": None,
                "for_next_stage": False,
            }
        )
    return {"files": [], "manifest": manifest}


@router.get("/{exp_id}/artifacts/{name}")
async def get_artifact(exp_id: str, name: str):
    maars = _load_maars()
    task_id = None
    for prefix in ("task_", "output_"):
        if name.startswith(prefix) and name.endswith(".json"):
            task_id = name[len(prefix) : -5]
            break
    if not task_id:
        raise HTTPException(status_code=404, detail="Artifact not found")
    output = await maars["get_task_artifact"](exp_id, task_id)
    if output is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return JSONResponse(content=output)


@router.get("/{exp_id}/history")
async def get_history(exp_id: str) -> Dict[str, Any]:
    return {"commits": []}


@router.post("/{exp_id}/feedback")
async def add_feedback(exp_id: str, payload: FeedbackRequest) -> Dict[str, Any]:
    ensure_maars_path()
    from db import DB_DIR

    plan_dir = Path(DB_DIR) / exp_id
    plan_dir.mkdir(parents=True, exist_ok=True)
    feedback_path = plan_dir / "feedback.json"
    entries: List[Dict[str, Any]] = []
    if feedback_path.exists():
        try:
            entries = json.loads(feedback_path.read_text(encoding="utf-8"))
        except Exception:
            entries = []

    entries.append(
        {
            "type": payload.type.lower(),
            "message": payload.message,
            "ts": int(time.time()),
        }
    )
    feedback_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return {"status": "queued"}
