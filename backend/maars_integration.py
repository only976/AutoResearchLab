import asyncio
import sys
from pathlib import Path

import socketio
from fastapi import FastAPI


def ensure_maars_path() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    maars_backend = repo_root / "maars" / "backend"
    maars_backend_str = str(maars_backend)
    if maars_backend_str in sys.path:
        sys.path.remove(maars_backend_str)
    sys.path.insert(0, maars_backend_str)
    return maars_backend


def attach_maars(app: FastAPI) -> socketio.AsyncServer:
    ensure_maars_path()

    from api import PlanRunState, register_routes
    from task_agent import ExecutionRunner

    sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
    plan_run_state = PlanRunState()
    plan_run_state.lock = asyncio.Lock()
    runner = ExecutionRunner(sio)

    register_routes(app, sio, runner, plan_run_state)

    # Socket.IO is exposed by wrapping the FastAPI app in `backend.main.asgi_app`.
    # Avoid mounting a sub-app here, because Starlette mount does not rewrite
    # paths in a way that Engine.IO expects for socket.io_path matching.

    return sio
