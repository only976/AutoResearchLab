import anyio

from task_agent.runner import ExecutionRunner


async def _run_rollback_keeps_upstream(monkeypatch):
    runner = ExecutionRunner(sio=None, session_id="test")

    task_1_1 = {"task_id": "1_1", "dependencies": [], "status": "done"}
    task_1_2 = {"task_id": "1_2", "dependencies": ["1_1"], "status": "execution-failed"}
    task_1_3 = {"task_id": "1_3", "dependencies": ["1_2"], "status": "undone"}

    runner.task_map = {
        "1_1": task_1_1,
        "1_2": task_1_2,
        "1_3": task_1_3,
    }
    runner.reverse_dependency_index = {
        "1_1": ["1_2"],
        "1_2": ["1_3"],
        "1_3": [],
    }

    runner.completed_tasks = {"1_1"}
    runner.pending_tasks = {"1_2", "1_3"}
    runner.running_tasks = set()

    released = []

    from task_agent import runner as runner_mod

    def fake_release(task_id):
        released.append(task_id)
        return task_id

    monkeypatch.setitem(runner_mod.worker_manager, "release_worker_by_task_id", fake_release)

    await runner._rollback_task(task_1_2)

    assert "1_1" in runner.completed_tasks
    assert runner.task_map["1_1"]["status"] == "done"
    assert "1_1" not in runner.pending_tasks

    assert runner.task_map["1_2"]["status"] == "undone"
    assert runner.task_map["1_3"]["status"] == "undone"
    assert "1_2" in runner.pending_tasks
    assert "1_3" in runner.pending_tasks

    assert "1_2" in released
    assert "1_3" in released
    assert "1_1" not in released


def test_rollback_only_resets_failed_and_downstream(monkeypatch):
    anyio.run(_run_rollback_keeps_upstream, monkeypatch)


async def _run_handle_task_error_emits_event(monkeypatch):
    runner = ExecutionRunner(sio=None, session_id="test")
    runner.task_map = {"1_1": {"task_id": "1_1", "status": "doing"}}
    runner.reverse_dependency_index = {"1_1": []}
    runner.completed_tasks = set()
    runner.running_tasks = {"1_1"}
    runner.pending_tasks = {"1_1"}

    emitted = []

    def fake_emit(event, data):
        emitted.append((event, data))

    runner._emit = fake_emit

    from task_agent import runner as runner_mod

    monkeypatch.setitem(runner_mod.worker_manager, "release_worker_by_task_id", lambda _task_id: None)

    await runner._handle_task_error({"task_id": "1_1"}, RuntimeError("boom"))

    task_error = [payload for event, payload in emitted if event == "task-error"]
    assert task_error, "Expected task-error event to be emitted"
    assert task_error[0].get("taskId") == "1_1"
    assert task_error[0].get("willRetry") is False
    assert "boom" in str(task_error[0].get("error"))


def test_handle_task_error_emits_task_error_event(monkeypatch):
    anyio.run(_run_handle_task_error_emits_event, monkeypatch)


async def _run_build_context_with_retry_memory():
    runner = ExecutionRunner(sio=None, session_id="test")
    runner.execution_run_id = "exec_x"
    runner._idea_text = "global objective"
    runner.chain_cache = [
        {"task_id": "1_1", "status": "doing"},
        {"task_id": "1_2", "status": "undone"},
        {"task_id": "2_1", "status": "done"},
    ]
    runner.completed_tasks = {"2_1"}

    task = {
        "task_id": "1_1",
        "description": "prepare datasets",
        "dependencies": ["2_1"],
        "output": {"format": "JSON", "description": "artifact"},
        "validation": {"criteria": ["non-empty"]},
    }

    await runner._record_task_attempt_failure(
        task_id="1_1",
        phase="execution",
        attempt=1,
        error="Agent reached max turns",
        will_retry=True,
    )

    context = runner._build_task_execution_context(task, {"dep": {"k": "v"}})

    assert context["globalGoal"] == "global objective"
    assert context["planContext"]["currentTaskId"] == "1_1"
    assert context["taskContract"]["outputFormat"] == "JSON"
    assert context["retryMemory"]["attempt"] == 1
    assert "max turns" in context["retryMemory"]["lastFailure"]


def test_build_task_execution_context_includes_retry_memory():
    anyio.run(_run_build_context_with_retry_memory)


async def _run_load_task_attempt_memories(monkeypatch):
    runner = ExecutionRunner(sio=None, session_id="test")
    runner.research_id = "research_x"

    async def fake_list(research_id, task_id=None):
        assert research_id == "research_x"
        assert task_id is None
        return [
            {
                "researchId": "research_x",
                "taskId": "1_1",
                "attempt": 1,
                "data": {
                    "attempt": 1,
                    "phase": "execution",
                    "error": "Agent reached max turns",
                    "willRetry": True,
                    "ts": 1000,
                },
                "updatedAt": 1000,
            }
        ]

    from task_agent import runner as runner_mod

    monkeypatch.setattr(runner_mod, "list_task_attempt_memories", fake_list)

    await runner._load_task_attempt_memories()
    history = runner.task_attempt_history.get("1_1") or []
    assert len(history) == 1
    assert history[0]["attempt"] == 1
    assert "max turns" in history[0]["error"]


def test_load_task_attempt_memories(monkeypatch):
    anyio.run(_run_load_task_attempt_memories, monkeypatch)
