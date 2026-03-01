"""Config API. Backend maintains config.json; frontend fetches and overwrites on save."""

from fastapi import APIRouter, Body

from backend.config import get_config, save_config

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
def get_config_route():
    """Return config.json contents (flat format for frontend)."""
    c = get_config()
    api_key = (c.get("llm_api_key") or "").strip()
    return {
        "llm_model": (c.get("llm_model") or "").strip() or "gemini-3-flash-preview",
        "llm_api_base": (c.get("llm_api_base") or "").strip() or None,
        "llm_api_key": (c.get("llm_api_key") or "").strip(),
        "llm_api_key_configured": bool(api_key),
        "frontend_port": int(c.get("frontend_port") or 3030),
    }


@router.post("")
def save_config_route(body: dict = Body(...)):
    """Overwrite config.json with request body."""
    save_config(body)
    return {"success": True}
