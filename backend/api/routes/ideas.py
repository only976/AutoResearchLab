"""Generate idea API (post-refine stage)."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from db import get_effective_config, get_idea, save_idea
from ideas.generate_service import generate_idea_output

from ..schemas import GenerateIdeaRequest

router = APIRouter()


@router.post("/generate")
async def generate_idea_route(body: GenerateIdeaRequest):
    payload = body.generate_idea_input
    idea_id = (body.idea_id or "").strip()
    if payload is None and idea_id:
        data = await get_idea(idea_id)
        if isinstance(data, dict):
            payload = data.get("generateIdeaInput")
    if payload is None:
        return JSONResponse(status_code=400, content={"error": "generateIdeaInput or ideaId with stored generateIdeaInput is required"})

    cfg = await get_effective_config()
    out = await generate_idea_output(payload, cfg)

    if idea_id:
        current = await get_idea(idea_id) or {}
        current["generateIdeaInput"] = payload
        current["generateIdeaOutput"] = out
        await save_idea(current, idea_id)

    return {"ideaId": idea_id or None, "output": out}

