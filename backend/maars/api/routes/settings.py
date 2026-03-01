"""Settings API routes. Backend maintains settings.json; frontend fetches and overwrites on save."""

from fastapi import APIRouter, Body

from db import get_settings, save_settings

router = APIRouter()


@router.get("")
async def get_settings_route():
    """Return settings.json contents."""
    settings = await get_settings()
    return {"settings": settings}


@router.post("")
async def save_settings_route(body: dict = Body(...)):
    """Overwrite settings.json with request body."""
    await save_settings(body)
    return {"success": True}
