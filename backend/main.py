from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.experiments import router as experiments_router
from backend.api.ideas import router as ideas_router
from backend.api.paper import router as paper_router
from backend.config import LLM_MODEL, LLM_API_BASE, LLM_API_KEY
from backend.public.sandbox.docker_sandbox import DockerSandbox

app = FastAPI(title="AutoResearchLab API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ideas_router)
app.include_router(experiments_router)
app.include_router(paper_router)

@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok"}

@app.get("/api/health/detail")
def health_detail() -> Dict[str, Any]:
    docker_ok = False
    docker_message = "Docker client not available. Is Docker running?"
    try:
        sandbox = DockerSandbox()
        if sandbox.client:
            try:
                sandbox.client.ping()
                docker_ok = True
                docker_message = "Docker is running"
            except Exception as exc:
                docker_message = str(exc)
    except Exception as exc:
        docker_message = str(exc)
    return {
        "backend": {"ok": True},
        "docker": {"ok": docker_ok, "message": docker_message},
    }

@app.get("/api/config")
def get_config() -> Dict[str, Any]:
    return {
        "llm_model": LLM_MODEL,
        "llm_api_base": LLM_API_BASE,
        "llm_api_key_configured": bool(LLM_API_KEY),
    }
