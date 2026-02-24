from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from backend.ideas.agent import IdeaAgent
from backend.api.common import parse_json_text
from backend.public.schemas.request_models import IdeaRefineRequest, IdeaGenerateRequest, SnapshotSaveRequest
from backend.ideas.snapshots import save_snapshot, list_snapshots, load_snapshot

router = APIRouter(prefix="/api/ideas")


@router.post("/refine")
def refine_ideas(payload: IdeaRefineRequest) -> Dict[str, Any]:
    agent = IdeaAgent()
    text = agent.refine_topic(payload.scope)
    return parse_json_text(text)


@router.post("/generate")
def generate_ideas(payload: IdeaGenerateRequest) -> Dict[str, Any]:
    agent = IdeaAgent()
    text = agent.generate_ideas(payload.scope)
    return parse_json_text(text)


@router.get("/snapshots")
def get_snapshots() -> Dict[str, Any]:
    return {"files": list_snapshots()}


@router.post("/snapshots")
def save_snapshot_api(payload: SnapshotSaveRequest) -> Dict[str, Any]:
    filename = save_snapshot(payload.refinement_data, payload.results)
    return {"file": filename}


@router.get("/snapshots/{name}")
def load_snapshot_api(name: str) -> Dict[str, Any]:
    data = load_snapshot(name)
    if not data:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return data
