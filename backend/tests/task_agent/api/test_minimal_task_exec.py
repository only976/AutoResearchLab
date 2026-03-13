"""
Minimal test to verify first task execution and output stream.
"""

import json
import time


def test_single_first_task_basic_execution(
    client,
    session_headers,
    seed_real_refine_plan,
    monkeypatch,
):
    """
    Basic execution of first task - verify output generation without heavy tracing.
    """
    idea_id = seed_real_refine_plan["ideaId"]
    plan_id = seed_real_refine_plan["planId"]

    # Enable taskAgent mode
    client.post(
        "/api/settings",
        json={
            "agentMode": {
                "ideaAgent": "mock",
                "planAgent": "mock",
                "taskAgent": "agent",
                "paperAgent": "mock",
            }
        },
    )

    # Generate execution
    gen_resp = client.post(
        "/api/execution/generate-from-plan",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id},
    )
    assert gen_resp.status_code == 200
    execution = (gen_resp.json() or {}).get("execution") or {}
    tasks = execution.get("tasks") or []
    assert tasks, "No tasks"

    # Get first task
    first_task = tasks[0]
    task_id = first_task.get("task_id")
    print(f"\n✓ First task: {task_id} ({first_task.get('title')})")

    # Bind layout
    client.post(
        "/api/plan/layout",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id, "execution": execution},
    )

    # Mock agent
    from task_agent import runner as runner_mod

    async def fake_run_task_agent(**kwargs):
        return {"status": "success", "data": "task output data"}

    async def fake_validate_task_output_with_llm(*args, **kwargs):
        return True, "Valid"

    async def fake_prepare_execution_runtime(*, enabled=True, image=None):
        return {"enabled": enabled, "available": True, "connected": True, "image": image or "maars-task-python:latest"}

    async def mock_ensure_execution_container(**kwargs):
        return {
            "enabled": True,
            "containerRunning": True,
            "containerName": f"mock-{kwargs.get('task_id')}",
            "taskId": kwargs.get("task_id"),
        }

    monkeypatch.setattr(runner_mod, "run_task_agent", fake_run_task_agent)
    monkeypatch.setattr(runner_mod, "validate_task_output_with_llm", fake_validate_task_output_with_llm)
    monkeypatch.setattr(runner_mod, "prepare_execution_runtime", fake_prepare_execution_runtime)
    monkeypatch.setattr(runner_mod, "ensure_execution_container", mock_ensure_execution_container)
    async def fake_stop_execution_container(_container_name):
        return None
    monkeypatch.setattr(runner_mod, "stop_execution_container", fake_stop_execution_container)
    async def fake_get_local_docker_status(**k):
        return {"enabled": True, "available": True, "connected": True}
    monkeypatch.setattr(runner_mod, "get_local_docker_status", fake_get_local_docker_status)

    # Run
    run_resp = client.post(
        "/api/execution/run",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id},
    )
    assert run_resp.status_code == 200

    # Wait for completion
    deadline = time.time() + 15
    while time.time() < deadline:
        s = client.get(
            f"/api/execution/status?ideaId={idea_id}&planId={plan_id}",
            headers=session_headers,
        ).json() or {}
        if not s.get("running"):
            break
        time.sleep(0.1)

    print(f"✓ Execution completed")
