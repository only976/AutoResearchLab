"""
Shared API state - sio, runner, plan run state.
Initialized by main.py after creating app and services.
"""

from typing import Any, Optional


class PlanRunState:
    """Mutable container for plan run abort/task state. Main holds refs for stop."""
    abort_event: Optional[Any] = None
    run_task: Optional[Any] = None
    lock: Optional[Any] = None


# Set by main.py
sio: Any = None
runner: Any = None
plan_run_state: Optional[PlanRunState] = None


def init_api_state(sio_instance, run_runner, run_state: PlanRunState):
    global sio, runner, plan_run_state
    sio = sio_instance
    runner = run_runner
    plan_run_state = run_state
