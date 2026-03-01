"""API route modules.

叙事口径：Idea、Plan、Task 为三个 Agent；Task Agent 含 Execution 与 Validation 两阶段。
/api/execution 为 Task Agent Execution 阶段入口。
"""

from fastapi import FastAPI

from . import db, execution, idea, plan, plans, settings, status
from ..state import PlanRunState, IdeaRunState, init_api_state


def register_routes(app: FastAPI, sio, run_runner, plan_run_state: PlanRunState, idea_run_state: IdeaRunState):
    """Register all API routers."""
    init_api_state(sio, run_runner, plan_run_state, idea_run_state)

    app.include_router(db.router, prefix="/api/db", tags=["db"])
    app.include_router(plan.router, prefix="/api/plan", tags=["plan-agent"])
    app.include_router(plans.router, prefix="/api/plans", tags=["plans"])
    app.include_router(execution.router, prefix="/api/execution", tags=["task-execution"])
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
    app.include_router(idea.router, prefix="/api/idea", tags=["idea-agent"])
    app.include_router(status.router, prefix="/api/status", tags=["status"])
