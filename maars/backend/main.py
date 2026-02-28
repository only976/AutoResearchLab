"""
MAARS Backend - FastAPI + Socket.io entry point.
Python implementation of the MAARS backend.
"""

import asyncio
from pathlib import Path

import socketio
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api import PlanRunState, register_routes
from task_agent import ExecutionRunner, worker_manager

# Socket.io
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
app = FastAPI(title="MAARS Backend")


@app.on_event("startup")
async def _print_browser_url():
    """Print the URL to open in browser (0.0.0.0 is not openable in browser)."""
    import sys
    print("INFO:     Open in browser: http://localhost:3001", file=sys.stderr, flush=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Plan run state (abort event, run task, lock)
plan_run_state = PlanRunState()
plan_run_state.lock = asyncio.Lock()

# Execution runner instance
runner = ExecutionRunner(sio)

# Register API routes (db, plan, plans, execution, settings)
register_routes(app, sio, runner, plan_run_state)


# Disable cache for static files (dev: always fetch latest)
NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.endswith((".html", ".css", ".js")):
            for k, v in NO_CACHE_HEADERS.items():
                response.headers[k] = v
        return response


app.add_middleware(NoCacheMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Centralized exception handler for unhandled errors."""
    logger.exception("Unhandled exception: {}", exc)
    return JSONResponse(
        status_code=500,
        content={"error": str(exc) or "Internal server error"},
    )


# Frontend static files
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")


# Socket.io events
@sio.event
async def connect(sid, environ, auth):
    logger.info("Client connected: %s", sid)
    stats = worker_manager["get_worker_stats"]()
    await sio.emit("execution-stats-update", {"stats": stats}, to=sid)


@sio.event
def disconnect(sid):
    logger.info("Client disconnected: %s", sid)


# ASGI app for uvicorn (Socket.io + FastAPI)
asgi_app = socketio.ASGIApp(sio, app)
