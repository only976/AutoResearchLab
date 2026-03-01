from typing import Any, Dict
from datetime import datetime

from fastapi import APIRouter, HTTPException

from backend.api.common import parse_json_text
from backend.ideas.agent import IdeaAgent
from backend.ideas.snapshots import load_snapshot, list_snapshots, save_snapshot
from backend.schemas.request_models import (
    IdeaGenerateRequest,
    IdeaRefineRequest,
    SnapshotSaveRequest,
)

router = APIRouter(prefix="/api/ideas")


def _fallback_topic_from_scope(scope: str) -> Dict[str, Any]:
    cleaned = (scope or "").strip()
    if not cleaned:
        return {"title": "Idea Snapshot", "scope": ""}

    one_line = " ".join(cleaned.split())
    title = one_line[:80]
    return {"title": title, "scope": cleaned}


def _build_snapshot_name_with_llm(agent: IdeaAgent, refined_topic: Any, snapshot_results: Any) -> str:
    llm_title = agent.generate_snapshot_title(refined_topic, snapshot_results)
    if not llm_title:
        llm_title = "idea_snapshot"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{llm_title}"


@router.post("/refine")
def refine_ideas(payload: IdeaRefineRequest) -> Dict[str, Any]:
    agent = IdeaAgent()
    text = agent.refine_topic(payload.scope)
    return parse_json_text(text)


@router.post("/generate")
def generate_ideas(payload: IdeaGenerateRequest) -> Dict[str, Any]:
    agent = IdeaAgent()
    text = agent.generate_ideas(payload.scope)
    result = parse_json_text(text)
    try:
        import json

        try:
            refined_topic = json.loads(payload.scope)
        except Exception:
            refined_topic = _fallback_topic_from_scope(payload.scope)

        ideas_list = result.get("ideas", []) if isinstance(result, dict) else result
        snapshot_results = [{"topic": refined_topic, "ideas": ideas_list}]
        snapshot_name = _build_snapshot_name_with_llm(agent, refined_topic, snapshot_results)
        save_snapshot(refined_topic, snapshot_results, custom_name=snapshot_name)
    except Exception:
        pass
    return result


@router.get("/snapshots")
def get_snapshots() -> Dict[str, Any]:
    """获取所有已保存的快照列表"""
    return {"files": list_snapshots()}


@router.post("/snapshots")
def save_snapshot_api(payload: SnapshotSaveRequest) -> Dict[str, Any]:
    agent = IdeaAgent()
    snapshot_name = _build_snapshot_name_with_llm(agent, payload.refinement_data, payload.results)
    filename = save_snapshot(payload.refinement_data, payload.results, custom_name=snapshot_name)
    return {"file": filename}


@router.get("/snapshots/{name}")
def load_snapshot_api(name: str) -> Dict[str, Any]:
    """加载特定的研究快照"""
    data = load_snapshot(name)
    if not data:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return data