from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from backend.maars_integration import ensure_maars_path
from backend.paper.writing_agent import WritingAgent
from backend.schemas.request_models import DraftRequest

router = APIRouter(prefix="/api/experiments")


def _maars_plan_to_paper_format(plan: dict) -> dict:
    """Convert MAARS plan shape to writing_agent expected format."""
    tasks = plan.get("tasks") or []
    return {
        "title": plan.get("idea") or "Untitled",
        "goal": plan.get("idea") or "N/A",
        "steps": [{"description": t.get("description", "")} for t in tasks],
    }


def _synthesize_conclusion_from_outputs(outputs: dict) -> dict:
    """Build conclusion dict from MAARS task outputs for paper draft."""
    findings = []
    for task_id, out in outputs.items():
        if isinstance(out, dict):
            content = out.get("content") or out.get("summary") or str(out)[:500]
            findings.append(f"Task {task_id}: {content}")
        else:
            findings.append(f"Task {task_id}: {str(out)[:500]}")
    return {
        "summary": "Synthesized from task outputs.",
        "key_findings": findings[:10],
        "recommendation": "Review and refine based on full task outputs.",
    }


async def _get_maars_plan_and_outputs(exp_id: str) -> tuple[dict | None, dict | None]:
    """Return (plan, outputs) from MAARS db if plan exists, else (None, None)."""
    ensure_maars_path()
    from db import get_plan, list_plan_outputs

    plan = await get_plan(exp_id)
    if not plan:
        return None, None
    outputs = await list_plan_outputs(exp_id)
    return plan, outputs


@router.post("/{exp_id}/draft")
async def generate_draft(exp_id: str, payload: DraftRequest) -> Dict[str, Any]:
    maars_plan, maars_outputs = await _get_maars_plan_and_outputs(exp_id)
    if not maars_plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan = _maars_plan_to_paper_format(maars_plan)
    conclusion = _synthesize_conclusion_from_outputs(maars_outputs or {})
    artifacts = [f"{tid}_output" for tid in (maars_outputs or {}).keys()]

    format_value = payload.format.lower()
    if format_value not in {"markdown", "latex"}:
        format_value = "markdown"
    agent = WritingAgent()
    draft = agent.generate_paper(plan, conclusion, artifacts, format=format_value)
    return {"format": format_value, "content": draft}
