"""Config API. Backend maintains config.json; frontend fetches and overwrites on save."""

from fastapi import APIRouter, Body

from backend.config import get_config, save_config

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
def get_config_route():
    """Return config.json contents."""
    config = get_config()
    return {"config": config}


@router.post("")
def save_config_route(body: dict = Body(...)):
    """Overwrite config.json with request body."""
    save_config(body)
    return {"success": True}
