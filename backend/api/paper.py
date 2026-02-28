import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from backend.paper.writing_agent import WritingAgent
from backend.api.common import ensure_experiment_path, read_json
from backend.db.repository import (
    get_experiment_conclusion as db_get_experiment_conclusion,
    get_experiment_plan as db_get_experiment_plan,
)
from backend.schemas.request_models import DraftRequest

router = APIRouter(prefix="/api/experiments")


@router.post("/{exp_id}/draft")
def generate_draft(exp_id: str, payload: DraftRequest) -> Dict[str, Any]:
    workspace_path = ensure_experiment_path(exp_id)
    plan = db_get_experiment_plan(exp_id) or read_json(os.path.join(workspace_path, "plan.json"))
    conclusion = db_get_experiment_conclusion(exp_id) or read_json(os.path.join(workspace_path, "conclusion.json"))
    if not plan or not conclusion:
        raise HTTPException(status_code=404, detail="Plan or conclusion missing")
    artifacts = [
        name
        for name in os.listdir(workspace_path)
        if name.endswith((".png", ".jpg", ".csv"))
    ]
    format_value = payload.format.lower()
    if format_value not in {"markdown", "latex"}:
        format_value = "markdown"
    agent = WritingAgent()
    draft = agent.generate_paper(plan, conclusion, artifacts, format=format_value)
    return {"format": format_value, "content": draft}
