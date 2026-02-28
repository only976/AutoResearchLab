from typing import Any, Dict
from datetime import datetime
from fastapi import APIRouter, HTTPException
from backend.ideas.agent import IdeaAgent
from backend.api.common import parse_json_text
from backend.schemas.request_models import IdeaRefineRequest, IdeaGenerateRequest, SnapshotSaveRequest
from backend.ideas.snapshots import save_snapshot, list_snapshots, load_snapshot
from backend.utils.logger import setup_logger

router = APIRouter(prefix="/api/ideas")
logger = setup_logger("ideas_api")


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
    logger.info("[ideas.refine] start scope_len=%s", len(payload.scope or ""))
    agent = IdeaAgent()
    text = agent.refine_topic(payload.scope)
    parsed = parse_json_text(text)
    topics = parsed.get("topics", []) if isinstance(parsed, dict) else []
    logger.info("[ideas.refine] done topics=%s has_error=%s", len(topics), bool(parsed.get("error")) if isinstance(parsed, dict) else False)
    return parsed


@router.post("/generate")
def generate_ideas(payload: IdeaGenerateRequest) -> Dict[str, Any]:
    logger.info("[ideas.generate] start scope_len=%s", len(payload.scope or ""))
    agent = IdeaAgent()
    text = agent.generate_ideas(payload.scope)
    result = parse_json_text(text)
    ideas_count = len(result.get("ideas", [])) if isinstance(result, dict) and isinstance(result.get("ideas"), list) else 0
    logger.info("[ideas.generate] parsed result_type=%s ideas_count=%s has_error=%s", type(result).__name__, ideas_count, bool(result.get("error")) if isinstance(result, dict) else False)
    if ideas_count == 0:
        preview = result
        if isinstance(result, dict):
            preview = {k: result[k] for k in list(result.keys())[:5]}
        logger.warning("[ideas.generate] empty ideas returned; result_keys=%s preview=%s", list(result.keys()) if isinstance(result, dict) else [], str(preview)[:500])
    
    # Auto-save the generated ideas
    try:
        import json
        # payload.scope is expected to be a JSON string of the refined topic
        try:
            refined_topic = json.loads(payload.scope)
        except Exception:
            # Fallback if scope is just a string
            refined_topic = _fallback_topic_from_scope(payload.scope)
            
        ideas_list = result.get("ideas", []) if isinstance(result, dict) else result
        
        # Structure matches what frontend expects for results
        snapshot_results = [{
            "topic": refined_topic,
            "ideas": ideas_list
        }]

        snapshot_name = _build_snapshot_name_with_llm(agent, refined_topic, snapshot_results)
        saved_name = save_snapshot(refined_topic, snapshot_results, custom_name=snapshot_name)
        logger.info("[ideas.generate] auto-saved snapshot=%s ideas_count=%s", saved_name, len(ideas_list) if isinstance(ideas_list, list) else 0)
    except Exception as e:
        logger.error("[ideas.generate] auto-save failed: %s", e, exc_info=True)
        
    return result


@router.get("/snapshots")
def get_snapshots() -> Dict[str, Any]:
    files = list_snapshots()
    logger.info("[ideas.snapshots] list count=%s", len(files))
    return {"files": files}


@router.post("/snapshots")
def save_snapshot_api(payload: SnapshotSaveRequest) -> Dict[str, Any]:
    agent = IdeaAgent()
    snapshot_name = _build_snapshot_name_with_llm(agent, payload.refinement_data, payload.results)
    filename = save_snapshot(payload.refinement_data, payload.results, custom_name=snapshot_name)
    ideas_count = 0
    if isinstance(payload.results, list) and payload.results:
        first = payload.results[0] if isinstance(payload.results[0], dict) else {}
        if isinstance(first.get("ideas"), list):
            ideas_count = len(first.get("ideas"))
    logger.info("[ideas.snapshots] manual save snapshot=%s ideas_count=%s", filename, ideas_count)
    return {"file": filename}


@router.get("/snapshots/{name}")
def load_snapshot_api(name: str) -> Dict[str, Any]:
    data = load_snapshot(name)
    if not data:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return data
