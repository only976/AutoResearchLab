"""
Test single task execution to diagnose agent output vs frontend display issues.
Execute task "1" (Data Preparation) and trace complete flow.
"""

import json
import time

from db import get_execution_task_src_dir, get_execution_task_step_dir


def test_single_task_1_data_preparation_execution_debug(
    client,
    session_headers,
    seed_real_refine_plan,
    monkeypatch,
):
    """
    Execute plan task "1" (Data Preparation) with extensive tracing.
    Capture:
    - Task agent input spec & output spec
    - Agent thinking events
    - Task output
    - Frontend event stream
    - Step events file content
    """
    idea_id = seed_real_refine_plan["ideaId"]
    plan_id = seed_real_refine_plan["planId"]

    # 1. Enable taskAgent mode
    set_resp = client.post(
        "/api/settings",
        json={
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
        },
    )
    assert set_resp.status_code == 200, f"Settings failed: {set_resp.text}"

    # 2. Generate execution + bind layout
    gen_resp = client.post(
        "/api/execution/generate-from-plan",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id},
    )
    assert gen_resp.status_code == 200
    execution = (gen_resp.json() or {}).get("execution") or {}
    tasks = execution.get("tasks") or []
    assert tasks, "No tasks in execution"

    # Debug: print all task ids
    all_task_ids = [t.get("task_id") for t in tasks]
    print(f"\n=== AVAILABLE TASK IDS: {all_task_ids} ===", flush=True)

    # Find task "1" - try fallback if "1" not found
    task_1 = next((t for t in tasks if t.get("task_id") == "1"), None)
    if task_1 is None:
        # If "1" not found, use first task
        task_1 = tasks[0] if tasks else None
        print(f"Task '1' not found, using first task: {task_1.get('task_id') if task_1 else None}", flush=True)
    assert task_1 is not None, f"No suitable task found. Available: {all_task_ids}"

    print(f"\n=== TASK SPEC ===", flush=True)
    print(f"Task ID: {task_1.get('task_id')}", flush=True)
    print(f"Title: {task_1.get('title')}", flush=True)
    print(f"Description: {task_1.get('description')[:200]}...", flush=True)
    print(f"Input spec: {json.dumps(task_1.get('input') or {}, indent=2)}", flush=True)
    print(f"Output spec: {json.dumps(task_1.get('output') or {}, indent=2)}", flush=True)

    layout_resp = client.post(
        "/api/plan/layout",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id, "execution": execution},
    )
    assert layout_resp.status_code == 200

    # 3. Monkeypatch runner to capture events and mock agent
    from task_agent import runner as runner_mod

    captured_events = []
    agent_output = None
    target_task_id = task_1.get("task_id")  # Dynamically capture the task ID

    original_emit = runner_mod.ExecutionRunner._emit

    def capture_emit(self, event, data):
        captured_events.append((event, json.dumps(data)))
        print(f"\n>>> EMIT: {event} = {json.dumps(data, indent=2)[:200]}...", flush=True)
        original_emit(self, event, data)

    async def mock_run_task_agent(**kwargs):
        task_id = kwargs.get("task_id")
        print(f"\n=== AGENT CALLED FOR TASK {task_id} ===", flush=True)
        print(f"docker_container_name: {kwargs.get('docker_container_name')}", flush=True)
        print(f"execution_run_id: {kwargs.get('execution_run_id')}", flush=True)

        # Simulate agent output
        nonlocal agent_output
        agent_output = {
            "datasets": [
                {"name": "Leukemia Gene Expression", "samples": 72, "features": 7129},
                {"name": "ORL Faces", "samples": 400, "features": 1024},
                {"name": "Wine Classification", "samples": 178, "features": 13},
                {"name": "Breast Cancer Wisconsin", "samples": 569, "features": 30},
            ],
            "preprocessing_steps": [
                "Loaded 4 datasets",
                "Applied Z-score standardization to all features",
                "Verified no missing values",
            ],
        }
        print(f"\n=== AGENT OUTPUT ===\n{json.dumps(agent_output, indent=2, ensure_ascii=False)}", flush=True)
        return agent_output

    async def mock_validate_task_output_with_llm(*args, **kwargs):
        return True, "Data preparation completed successfully"

    async def mock_ensure_execution_container(**kwargs):
        task_id = kwargs.get("task_id", target_task_id)
        execution_run_id = kwargs.get("execution_run_id")
        return {
            "enabled": True,
            "available": True,
            "connected": True,
            "containerRunning": True,
            "containerName": f"maars-task-{execution_run_id}-{task_id}",
            "image": "python:3.11-slim",
            "taskId": task_id,
            "srcDir": str(get_execution_task_src_dir(execution_run_id, task_id).resolve()),
            "stepDir": str(get_execution_task_step_dir(execution_run_id, task_id).resolve()),
            "sandboxRoot": str(get_execution_task_step_dir(execution_run_id, task_id).resolve().parent.parent.parent),
        }

    async def mock_stop_execution_container(container_name):
        pass

    async def mock_get_local_docker_status(**kwargs):
        return {
            "enabled": True,
            "available": True,
            "connected": True,
            "containerRunning": True,
            "containerName": "",
            "image": "python:3.11-slim",
            "dockerPath": "docker",
            "serverVersion": "test",
        }

    async def mock_prepare_execution_runtime(*, enabled=True, image=None):
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

    monkeypatch.setattr(runner_mod.ExecutionRunner, "_emit", capture_emit)
    monkeypatch.setattr(runner_mod, "run_task_agent", mock_run_task_agent)
    monkeypatch.setattr(runner_mod, "validate_task_output_with_llm", mock_validate_task_output_with_llm)
    monkeypatch.setattr(runner_mod, "prepare_execution_runtime", mock_prepare_execution_runtime)
    monkeypatch.setattr(runner_mod, "ensure_execution_container", mock_ensure_execution_container)
    monkeypatch.setattr(runner_mod, "stop_execution_container", mock_stop_execution_container)
    monkeypatch.setattr(runner_mod, "get_local_docker_status", mock_get_local_docker_status)

    # 4. Run execution
    run_resp = client.post(
        "/api/execution/run",
        headers=session_headers,
        json={"ideaId": idea_id, "planId": plan_id},
    )
    assert run_resp.status_code == 200, f"Execution run failed: {run_resp.text}"

    # 5. Wait for completion
    deadline = time.time() + 30
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
        time.sleep(0.2)

    assert final_status is not None
    print(f"\n=== FINAL EXECUTION STATUS ===\n{json.dumps(final_status, indent=2)}", flush=True)

    # 6. Check task state
    task_states = final_status.get("tasks") or []
    task_1_state = next((t for t in task_states if t.get("task_id") == target_task_id), None)
    assert task_1_state is not None, f"Task {target_task_id} not in final status"
    print(f"\n=== TASK 1 FINAL STATE ===\n{json.dumps(task_1_state, indent=2)}", flush=True)

    # 7. Check captured events
    print(f"\n=== CAPTURED EVENTS ({len(captured_events)} total) ===", flush=True)
    for i, (event, data_str) in enumerate(captured_events):
        print(f"{i}. {event}: {data_str[:150]}...", flush=True)

    # 8. Check step events file
    run_id = next((json.loads(data).get("executionRunId") for event, data in captured_events if event == "execution-runtime-status"), None)
    assert run_id, "No executionRunId captured from runtime status"
    step_file = (get_execution_task_step_dir(run_id, target_task_id) / "events.jsonl").resolve()
    print(f"\n=== CHECKING STEP EVENTS FILE ===")
    print(f"Path: {step_file}", flush=True)
    print(f"Exists: {step_file.exists()}", flush=True)

    if step_file.exists():
        lines = [line for line in step_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        print(f"Line count: {len(lines)}", flush=True)
        for i, line in enumerate(lines[:10]):
            try:
                ev = json.loads(line)
                print(f"  {i}. {ev.get('event')}: {str(ev.get('data', {}))[:100]}", flush=True)
            except:
                print(f"  {i}. [parse error]: {line[:100]}", flush=True)

    # 9. Assertions
    assert captured_events, "No events captured"
    event_names = [e[0] for e in captured_events]
    print(f"\nEvent names: {event_names}", flush=True)
    assert "task-started" in event_names, f"No task-started event. Events: {event_names}"
    assert "task-completed" in event_names or "task-output" in event_names, f"No task-completed/output. Events: {event_names}"

    assert agent_output is not None, "Agent output is None"
    assert isinstance(agent_output, dict), "Agent output should be dict"
    assert "datasets" in agent_output, "Agent output missing 'datasets'"

    assert step_file.exists(), f"Step events file not found: {step_file}"

    print(f"\n✓ Single task execution debug complete", flush=True)
