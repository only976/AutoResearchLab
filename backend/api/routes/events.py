"""SSE events stream.

This replaces the Socket.IO client for pushing realtime events (thinking chunks,
agent completion/error, task state updates) to the frontend.

Endpoint: GET /api/events/stream?sessionId=...&sessionToken=...
"""

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .. import state as api_state


router = APIRouter()


def _sse_format(event: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    # SSE requires each line of data prefixed with 'data: '
    lines = str(payload).splitlines() or [""]
    data_lines = "\n".join(f"data: {line}" for line in lines)
    return f"event: {event}\n{data_lines}\n\n"


@router.get("/stream")
async def stream_events(request: Request):
    """Stream realtime events for the authenticated session via SSE."""
    session_id, _session = await api_state.require_session(request)
    q = api_state.subscribe_sse(session_id)

    async def gen() -> AsyncIterator[bytes]:
        try:
            # Ask browser to retry quickly on disconnect
            yield b"retry: 1000\n\n"
            # Initial marker event
            yield _sse_format("sse-open", {"sessionId": session_id}).encode("utf-8")
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event, payload, _ts = await asyncio.wait_for(q.get(), timeout=15)
                    yield _sse_format(event, payload).encode("utf-8")
                except asyncio.TimeoutError:
                    # Keep-alive comment to prevent some proxies from closing the connection
                    yield b": keep-alive\n\n"
        finally:
            api_state.unsubscribe_sse(session_id, q)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        # Nginx: disable response buffering for SSE
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
