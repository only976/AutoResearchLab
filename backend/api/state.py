"""
Shared API state - sio, runner, Plan/Idea Agent run state.
Initialized by main.py after creating app and services.
"""

from typing import Any, Optional


class PlanRunState:
    """Plan Agent 运行状态：abort 信号、run_task。供 /api/plan/stop 使用。"""
    abort_event: Optional[Any] = None
    run_task: Optional[Any] = None
    lock: Optional[Any] = None


class IdeaRunState:
    """Idea Agent 运行状态：run_task、abort_event。供 /api/idea/stop 使用。"""
    run_task: Optional[Any] = None
    abort_event: Optional[Any] = None


# Set by main.py
sio: Any = None
runner: Any = None  # Task Agent Execution 阶段 runner
plan_run_state: Optional[PlanRunState] = None
idea_run_state: Optional[IdeaRunState] = None


def init_api_state(sio_instance, run_runner, run_state: PlanRunState, idea_run_state_ref: Optional[IdeaRunState] = None):
    global sio, runner, plan_run_state, idea_run_state
    sio = sio_instance
    runner = run_runner
    plan_run_state = run_state
    idea_run_state = idea_run_state_ref
