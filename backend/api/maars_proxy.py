import asyncio
import json
import os
from typing import AsyncIterator, Dict, Optional

import httpx
import socketio
from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

router = APIRouter()

MAARS_BASE_URL = os.getenv("MAARS_BASE_URL")
MAARS_SOCKETIO_PATH = os.getenv("MAARS_SOCKETIO_PATH", "/maars/socket.io")


def _resolve_base_url(request: Request) -> str:
    if MAARS_BASE_URL:
        return MAARS_BASE_URL.rstrip("/")
    return str(request.base_url).rstrip("/")


def _build_upstream_url(base_url: str, path: str) -> str:
    path = path.lstrip("/")
    return f"{base_url}/api/{path}"


@router.get("/api/maars/events")
async def maars_events(request: Request) -> StreamingResponse:
    """SSE bridge: convert Socket.IO events into EventSource SSE events.

    Important: this route must be registered before the catch-all
    `/api/maars/{path:path}` proxy, otherwise it will be shadowed.
    """
    plan_id = request.query_params.get("planId")
    base_url = _resolve_base_url(request)
    generator = _sse_event_stream(base_url, plan_id)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.api_route("/api/maars/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_maars_api(path: str, request: Request) -> Response:
    base_url = _resolve_base_url(request)
    url = _build_upstream_url(base_url, path)
    method = request.method.upper()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}
    params = dict(request.query_params)
    body = await request.body()

    async with httpx.AsyncClient(timeout=60.0) as client:
        upstream = await client.request(method, url, headers=headers, params=params, content=body)

    response_headers = {"Content-Type": upstream.headers.get("content-type", "application/json")}
    return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)


async def _sse_event_stream(base_url: str, plan_id: Optional[str] = None) -> AsyncIterator[str]:
    queue: asyncio.Queue = asyncio.Queue()
    sio = socketio.AsyncClient(reconnection=True, reconnection_attempts=10, reconnection_delay=1)

    events = [
        "plan-start",
        "plan-thinking",
        "plan-tree-update",
        "plan-complete",
        "plan-error",
        "execution-layout",
        "task-states-update",
        "task-thinking",
        "task-output",
        "execution-stats-update",
        "execution-error",
        "execution-complete",
    ]

    async def _enqueue(event_name: str, data: Dict) -> None:
        payload = {"event": event_name, "data": data}
        await queue.put(payload)

    for event_name in events:
        sio.on(event_name, handler=lambda data, name=event_name: asyncio.create_task(_enqueue(name, data)))

    async def _connect() -> None:
        await sio.connect(base_url, socketio_path=MAARS_SOCKETIO_PATH)
        if plan_id:
            await queue.put({"event": "plan-id", "data": {"planId": plan_id}})

    await _connect()

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(15)
            await queue.put({"event": "ping", "data": {"ts": int(asyncio.get_event_loop().time())}})

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        while True:
            item = await queue.get()
            event_name = item.get("event", "message")
            data = item.get("data", {})
            yield f"event: {event_name}\n"
            yield f"data: {json.dumps(data, ensure_ascii=True)}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        heartbeat_task.cancel()
        try:
            await sio.disconnect()
        except Exception:
            pass


@router.get("/api/maars/events")
async def maars_events(request: Request) -> StreamingResponse:
    plan_id = request.query_params.get("planId")
    base_url = _resolve_base_url(request)
    generator = _sse_event_stream(base_url, plan_id)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
