"""DB API routes."""

from fastapi import APIRouter

from db import clear_db

router = APIRouter()


@router.post("/clear")
async def clear():
    """Clear DB: remove all plan folders."""
    return await clear_db()
