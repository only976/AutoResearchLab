"""Plans list API - GET /api/plans."""

from fastapi import APIRouter

from db import list_plan_ids

router = APIRouter()


@router.get("")
async def list_plans():
    """List plan IDs (newest first). Used when localStorage has no plan to restore latest."""
    ids = await list_plan_ids()
    return {"planIds": ids}
