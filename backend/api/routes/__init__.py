"""API route modules.

叙事口径：Idea、Plan、Task、Paper 为四个 Agent；Task Agent 含 Execution 与 Validation 两阶段。
/api/execution 为 Task Agent Execution 阶段入口。
"""

from fastapi import FastAPI

from . import db, events, execution, idea, log, paper, plan, plans, research, session, settings, status
from ..state import init_api_state


def register_routes(
    app: FastAPI,
    sio,
):
    """Register all API routers."""
    init_api_state(sio)

    app.include_router(db.router, prefix="/api/db", tags=["db"])
    app.include_router(session.router, prefix="/api/session", tags=["session"])
    app.include_router(events.router, prefix="/api/events", tags=["events"])
    app.include_router(plan.router, prefix="/api/plan", tags=["plan-agent"])
    app.include_router(plans.router, prefix="/api/plans", tags=["plans"])
    app.include_router(execution.router, prefix="/api/execution", tags=["task-execution"])
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
    app.include_router(log.router, prefix="/api/log", tags=["log"])
    app.include_router(research.router, prefix="/api/research", tags=["research"])
    app.include_router(idea.router, prefix="/api/idea", tags=["idea-agent"])
    app.include_router(paper.router, prefix="/api/paper", tags=["paper-agent"])
    app.include_router(status.router, prefix="/api/status", tags=["status"])
