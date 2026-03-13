from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from api import state as api_state
from shared.logging_config import append_frontend_log_records, build_frontend_log_record


router = APIRouter()


class FrontendLogEntry(BaseModel):
    level: str = Field(default="info")
    message: str
    ts: Optional[float] = None
    url: Optional[str] = None
    context: Optional[dict[str, Any]] = None


class FrontendLogPayload(BaseModel):
    entries: list[FrontendLogEntry] = Field(default_factory=list)


@router.post("/frontend")
async def post_frontend_logs(payload: FrontendLogPayload, request: Request):
    session_id, _session = await api_state.require_session(request)

    records = [
        build_frontend_log_record(
            session_id=session_id,
            level=e.level,
            message=e.message,
            url=e.url,
            ts=e.ts,
            context=e.context,
        )
        for e in (payload.entries or [])
        if e and e.message
    ]

    if records:
        append_frontend_log_records(records)

    return {"ok": True, "count": len(records)}
