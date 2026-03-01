"""Plans list API - GET /api/plans."""

from fastapi import APIRouter

from db import list_recent_plans

router = APIRouter()


@router.get("")
async def list_plans():
    """List (ideaId, planId) pairs (newest first). Used when localStorage has no plan to restore latest."""
    items = await list_recent_plans()
    return {"items": items}
