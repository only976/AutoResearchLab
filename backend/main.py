from typing import Any, Dict

from fastapi import FastAPI
import socketio
from fastapi.middleware.cors import CORSMiddleware

from backend.api.experiments import router as experiments_router
from backend.api.ideas import router as ideas_router
from backend.api.paper import router as paper_router
from backend.api.maars_proxy import router as maars_router
from backend.api.config import router as config_router
from backend.db import init_db
from backend.maars_integration import attach_maars

app = FastAPI(title="AutoResearchLab API", version="0.1.0")

init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ideas_router)
app.include_router(experiments_router)
app.include_router(paper_router)
app.include_router(maars_router)
app.include_router(config_router)
sio = attach_maars(app)

# Expose Socket.IO at /maars/socket.io while preserving all FastAPI routes.
asgi_app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="maars/socket.io")

@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok"}

@app.get("/api/health/detail")
def health_detail() -> Dict[str, Any]:
    docker_ok = False
    docker_message = "Docker sandbox not configured (MAARS uses file-based execution)"
    try:
        import docker
        client = docker.from_env()
        client.ping()
        docker_ok = True
        docker_message = "Docker is running"
    except Exception as exc:
        docker_message = str(exc)
    return {
        "backend": {"ok": True},
        "docker": {"ok": docker_ok, "message": docker_message},
    }

