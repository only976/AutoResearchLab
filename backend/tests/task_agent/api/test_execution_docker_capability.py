import json
import time

from db import get_execution_task_step_dir, get_execution_task_src_dir


def _agent_mode_settings_payload() -> dict:
    return {
        "theme": "light",
        "agentMode": {
            "ideaAgent": "mock",
            "planAgent": "mock",
            "taskAgent": "agent",
            "paperAgent": "mock",
            "ideaRAG": False,
        },
        "reflection": {"enabled": False, "maxIterations": 1, "qualityThreshold": 70},
        "current": "test",
        "presets": {
            "test": {
                "label": "test",
                "baseUrl": "",
                "apiKey": "dummy-key",
                "model": "mock-model",
            }
        },
    }


def test_execution_run_uses_task_docker_flow_and_writes_step_events(
    client,
    session_headers,
    seed_real_refine_plan,
    monkeypatch,
):
    # Enable taskAgentMode=True through settings
    set_resp = client.post("/api/settings", json=_agent_mode_settings_payload())
    assert set_resp.status_code == 200

    idea_id = seed_real_refine_plan["ideaId"]
    plan_id = seed_real_refine_plan["planId"]

    # Build execution graph and bind it to runner via plan/layout
    gen_resp = client.post(
        "/api/execution/generate-from-plan",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id},
    )
    assert gen_resp.status_code == 200
    execution = (gen_resp.json() or {}).get("execution") or {}
    tasks = execution.get("tasks") or []
    assert tasks

    layout_resp = client.post(
        "/api/plan/layout",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id, "execution": execution},
    )
    assert layout_resp.status_code == 200

    # Patch runtime pieces so test is deterministic and offline
    from task_agent import runner as runner_mod

    ensure_calls = []
    run_agent_calls = []
    stop_calls = []

    async def fake_get_local_docker_status(*, enabled=True, container_name=None):
        return {
            "enabled": enabled,
            "available": True,
            "connected": True,
            "containerRunning": bool(container_name),
            "containerName": container_name or "",
            "image": "python:3.11-slim",
            "dockerPath": "docker",
            "serverVersion": "test",
        }

    async def fake_prepare_execution_runtime(*, enabled=True, image=None):
        return {
            "enabled": enabled,
            "available": True,
            "connected": True,
            "containerRunning": False,
            "containerName": "",
            "image": image or "maars-task-python:latest",
            "dockerPath": "docker",
            "serverVersion": "test",
        }

    async def fake_ensure_execution_container(
        *,
        execution_run_id,
        idea_id,
        plan_id,
        task_id,
        skills_dir,
        image=None,
    ):
        ensure_calls.append(
            {
                "execution_run_id": execution_run_id,
                "idea_id": idea_id,
                "plan_id": plan_id,
                "task_id": task_id,
                "src_dir": str(get_execution_task_src_dir(execution_run_id, task_id).resolve()),
                "step_dir": str(get_execution_task_step_dir(execution_run_id, task_id).resolve()),
            }
        )
        return {
            "enabled": True,
            "available": True,
            "connected": True,
            "containerRunning": True,
            "containerName": f"maars-task-{execution_run_id}-{task_id}",
            "image": image or "python:3.11-slim",
            "taskId": task_id,
            "srcDir": str(get_execution_task_src_dir(execution_run_id, task_id).resolve()),
            "stepDir": str(get_execution_task_step_dir(execution_run_id, task_id).resolve()),
            "sandboxRoot": str(get_execution_task_step_dir(execution_run_id, task_id).resolve().parent.parent.parent),
        }

    async def fake_run_task_agent(**kwargs):
        run_agent_calls.append(kwargs)
        task_id = kwargs.get("task_id") or "unknown"
        return {"content": f"docker-agent-output-{task_id}"}

    async def fake_validate_task_output_with_llm(*args, **kwargs):
        return True, "ok"

    async def fake_stop_execution_container(container_name):
        stop_calls.append(container_name)

    monkeypatch.setattr(runner_mod, "get_local_docker_status", fake_get_local_docker_status)
    monkeypatch.setattr(runner_mod, "prepare_execution_runtime", fake_prepare_execution_runtime)
    monkeypatch.setattr(runner_mod, "ensure_execution_container", fake_ensure_execution_container)
    monkeypatch.setattr(runner_mod, "run_task_agent", fake_run_task_agent)
    monkeypatch.setattr(runner_mod, "validate_task_output_with_llm", fake_validate_task_output_with_llm)
    monkeypatch.setattr(runner_mod, "stop_execution_container", fake_stop_execution_container)

    run_resp = client.post(
        "/api/execution/run",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id},
    )
    assert run_resp.status_code == 200

    # Wait until execution finishes
    deadline = time.time() + 15
    final_status = None
    while time.time() < deadline:
        status_resp = client.get(
            f"/api/execution/status?ideaId={idea_id}&planId={plan_id}",
            headers=session_headers,
        )
        assert status_resp.status_code == 200
        final_status = status_resp.json() or {}
        if not final_status.get("running"):
            break
        time.sleep(0.1)

    assert final_status is not None
    task_states = final_status.get("tasks") or []
    assert task_states
    assert all((t.get("status") in ("done", "execution-failed", "validation-failed")) for t in task_states)

    # Docker capability checks
    assert ensure_calls, "Expected per-task container provisioning calls"
    assert run_agent_calls, "Expected task agent calls"
    assert stop_calls, "Expected task containers to be stopped"
    assert len({c["src_dir"] for c in ensure_calls}) == 1, "One execution should share a single src directory"

    first_call = run_agent_calls[0]
    assert first_call.get("docker_container_name"), "Task agent call should receive docker container name"
    assert str(first_call.get("execution_run_id", "")).startswith("exec_"), "execution_run_id should be populated"

    # Step event persistence checks
    first_task_id = ensure_calls[0]["task_id"]
    execution_run_id = ensure_calls[0]["execution_run_id"]
    step_file = (get_execution_task_step_dir(execution_run_id, first_task_id) / "events.jsonl").resolve()
    assert step_file.exists(), f"Missing step events file: {step_file}"

    lines = [line for line in step_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, "Step events file should not be empty"
    events = [json.loads(line).get("event") for line in lines]
    assert "task-started" in events
    assert ("task-completed" in events) or ("task-validation" in events)
