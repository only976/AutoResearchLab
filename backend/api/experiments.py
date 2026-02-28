import os
import subprocess
import uuid
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from backend.experiments.agents.experiment_design_agent import ExperimentDesignAgent
from backend.api.common import (
    EXPERIMENTS_DIR,
    ensure_dir,
    read_json,
    write_json,
    parse_json_text,
    get_workspace_path,
    ensure_experiment_path,
    safe_artifact_path,
)
from backend.experiments.execution.experiment_runner import start_experiment_background
from backend.experiments.execution.feedback_manager import FeedbackManager
from backend.db.repository import (
    get_experiment as db_get_experiment,
    get_experiment_conclusion as db_get_experiment_conclusion,
    get_experiment_logs as db_get_experiment_logs,
    get_experiment_plan as db_get_experiment_plan,
    get_experiment_status as db_get_experiment_status,
    list_experiment_artifacts as db_list_experiment_artifacts,
    list_experiment_rows as db_list_experiment_rows,
    upsert_experiment as db_upsert_experiment,
    upsert_experiment_plan as db_upsert_experiment_plan,
    upsert_experiment_status as db_upsert_experiment_status,
)
from backend.schemas.request_models import (
    ExperimentCreateRequest,
    ExperimentPlanRequest,
    ExperimentRunRequest,
    FeedbackRequest,
)

router = APIRouter(prefix="/api/experiments")

# Keep a symbol for legacy tests/tools that patch this name.
list_experiments = db_list_experiment_rows


@router.get("")
def get_experiments() -> List[Dict[str, Any]]:
    return list_experiments()


@router.get("/{exp_id}/meta")
def get_experiment_meta(exp_id: str) -> Dict[str, Any]:
    meta_row = db_get_experiment(exp_id)
    meta = meta_row["meta"] if meta_row else None
    if not meta:
        workspace_path = ensure_experiment_path(exp_id)
        meta = read_json(os.path.join(workspace_path, "meta.json"))
    if not meta:
        raise HTTPException(status_code=404, detail="Meta not found")
    return meta


@router.get("/{exp_id}/plan")
def get_experiment_plan(exp_id: str) -> Dict[str, Any]:
    plan = db_get_experiment_plan(exp_id)
    if not plan:
        workspace_path = ensure_experiment_path(exp_id)
        plan = read_json(os.path.join(workspace_path, "plan.json"))
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.get("/{exp_id}/conclusion")
def get_experiment_conclusion(exp_id: str) -> Dict[str, Any]:
    conclusion = db_get_experiment_conclusion(exp_id)
    if not conclusion:
        workspace_path = ensure_experiment_path(exp_id)
        conclusion = read_json(os.path.join(workspace_path, "conclusion.json"))
    if not conclusion:
        raise HTTPException(status_code=404, detail="Conclusion not found")
    return conclusion


@router.post("")
def create_experiment(payload: ExperimentCreateRequest) -> Dict[str, Any]:
    ensure_dir(EXPERIMENTS_DIR)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exp_id = f"exp_{timestamp}_{str(uuid.uuid4())[:8]}"
    workspace_path = get_workspace_path(exp_id)
    ensure_dir(workspace_path)
    meta_payload = {"id": exp_id, "idea": payload.idea, "topic": payload.topic}
    write_json(os.path.join(workspace_path, "meta.json"), meta_payload)
    db_upsert_experiment(exp_id, meta_payload)
    return {"id": exp_id}


@router.post("/{exp_id}/plan")
def generate_plan(exp_id: str, payload: ExperimentPlanRequest) -> Dict[str, Any]:
    workspace_path = get_workspace_path(exp_id)
    if not os.path.exists(workspace_path):
        raise HTTPException(status_code=404, detail="Experiment not found")
    agent = ExperimentDesignAgent()
    plan_text = agent.refine_plan(payload.idea, payload.topic or {})
    plan = parse_json_text(plan_text)
    write_json(os.path.join(workspace_path, "plan.json"), plan)
    db_upsert_experiment_plan(exp_id, plan)
    return plan


@router.post("/{exp_id}/run")
def run_experiment(exp_id: str, payload: ExperimentRunRequest) -> Dict[str, Any]:
    workspace_path = get_workspace_path(exp_id)
    plan = db_get_experiment_plan(exp_id) or read_json(os.path.join(workspace_path, "plan.json"))
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if payload.max_iterations is not None:
        status_path = os.path.join(workspace_path, "status.json")
        status = read_json(status_path) or {}
        status["max_iterations"] = payload.max_iterations
        write_json(status_path, status)
        db_upsert_experiment_status(exp_id, status)
    start_experiment_background(workspace_path, plan)
    return {"status": "started"}


@router.get("/{exp_id}/status")
def get_status(exp_id: str) -> Dict[str, Any]:
    status = db_get_experiment_status(exp_id)
    if not status:
        workspace_path = get_workspace_path(exp_id)
        status = read_json(os.path.join(workspace_path, "status.json"))
    if not status:
        return {
            "experiment_status": "initialized",
            "current_step": 0,
            "total_steps": 0,
            "step_name": "Initializing",
            "details": "Waiting for execution to start..."
        }
    return status


@router.get("/{exp_id}/logs")
def get_logs(exp_id: str, lines: int = Query(default=200, ge=1, le=2000)) -> Dict[str, Any]:
    db_lines = db_get_experiment_logs(exp_id, lines)
    if db_lines:
        return {"lines": db_lines}

    workspace_path = get_workspace_path(exp_id)
    log_path = os.path.join(workspace_path, "execution.log")
    if not os.path.exists(log_path):
        return {"lines": []}
    with open(log_path, "r") as f:
        content = f.readlines()
    return {"lines": content[-lines:]}


@router.get("/{exp_id}/artifacts")
def get_artifacts(exp_id: str) -> Dict[str, Any]:
    workspace_path = ensure_experiment_path(exp_id)
    files = []
    for name in os.listdir(workspace_path):
        if name.endswith((".png", ".jpg", ".csv", ".json")):
            files.append(name)
    manifest = db_list_experiment_artifacts(exp_id)
    return {"files": sorted(files), "manifest": manifest}


@router.get("/{exp_id}/artifacts/{name}")
def get_artifact(exp_id: str, name: str):
    workspace_path = ensure_experiment_path(exp_id)
    path = safe_artifact_path(workspace_path, name)
    return FileResponse(path)


@router.get("/{exp_id}/history")
def get_history(exp_id: str) -> Dict[str, Any]:
    workspace_path = ensure_experiment_path(exp_id)
    if not os.path.exists(os.path.join(workspace_path, ".git")):
        return {"commits": []}
    result = subprocess.run(
        ["git", "log", "--pretty=format:%h|%s|%cr|%an", "-n", "20"],
        cwd=workspace_path,
        stdout=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        return {"commits": []}
    commits = []
    for line in result.stdout.strip().split("\n"):
        parts = line.split("|")
        if len(parts) == 4:
            commits.append(
                {
                    "sha": parts[0],
                    "message": parts[1],
                    "time": parts[2],
                    "author": parts[3],
                }
            )
    return {"commits": commits}


@router.post("/{exp_id}/feedback")
def add_feedback(exp_id: str, payload: FeedbackRequest) -> Dict[str, Any]:
    workspace_path = ensure_experiment_path(exp_id)
    fm = FeedbackManager(workspace_path)
    fm.add_feedback(payload.type.lower(), payload.message)
    return {"status": "queued"}
