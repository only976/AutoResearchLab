"""API route modules."""

from fastapi import FastAPI

from . import db, execution, plan, plans, settings
from ..state import PlanRunState, init_api_state


def register_routes(app: FastAPI, sio, run_runner, plan_run_state: PlanRunState):
    """Register all API routers."""
    init_api_state(sio, run_runner, plan_run_state)

    app.include_router(db.router, prefix="/api/db", tags=["db"])
    app.include_router(plan.router, prefix="/api/plan", tags=["plan"])
    app.include_router(plans.router, prefix="/api/plans", tags=["plans"])
    app.include_router(execution.router, prefix="/api/execution", tags=["execution"])
    app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
