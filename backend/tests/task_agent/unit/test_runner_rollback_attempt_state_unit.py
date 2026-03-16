import asyncio

import anyio

from task_agent.runner import ExecutionRunner


async def _run_retry_task_clears_forced_attempt_on_reset(monkeypatch):
    runner = ExecutionRunner(sio=None, session_id="test")
    runner.idea_id = "idea_x"
    runner.plan_id = "plan_y"
    runner.is_running = True
    runner.task_map = {
        "1_1": {"task_id": "1_1", "dependencies": [], "status": "done"},
        "1_2_1": {"task_id": "1_2_1", "dependencies": ["1_1"], "status": "validation-failed"},
        "1_2_2": {"task_id": "1_2_2", "dependencies": ["1_2_1"], "status": "undone"},
    }
    runner.reverse_dependency_index = {
        "1_1": ["1_2_1"],
        "1_2_1": ["1_2_2"],
        "1_2_2": [],
    }
    runner.completed_tasks = {"1_1"}
    runner.pending_tasks = {"1_2_1", "1_2_2"}
    runner.running_tasks = set()
    runner.task_forced_attempt = {"1_2_1": 3, "1_2_2": 4}

    from task_agent import runner as runner_mod

    monkeypatch.setitem(runner_mod.worker_manager, "release_worker_by_task_id", lambda _task_id: None)

    async def fake_delete_artifact(*_args, **_kwargs):
        return None

    async def fake_clear_memories(*_args, **_kwargs):
        return None

    monkeypatch.setattr(runner_mod, "delete_task_artifact", fake_delete_artifact)
    monkeypatch.setattr(runner_mod, "delete_task_attempt_memories", fake_clear_memories)

    ok = await runner.retry_task("1_2_1")
    assert ok is True
    assert "1_2_1" not in runner.task_forced_attempt
    assert "1_2_2" not in runner.task_forced_attempt


def test_retry_task_clears_forced_attempt_on_reset(monkeypatch):
    anyio.run(_run_retry_task_clears_forced_attempt_on_reset, monkeypatch)


def test_resolve_run_attempt_uses_max_hint_and_forced():
    runner = ExecutionRunner(sio=None, session_id="test")
    runner.task_attempt_history["1_2_1"] = [{"attempt": 1, "phase": "validation", "ts": 1}]
    runner.task_forced_attempt["1_2_1"] = 2
    runner.task_next_attempt_hint["1_2_1"] = 3

    run_attempt = runner._resolve_run_attempt("1_2_1")
    assert run_attempt == 3
    assert runner.task_next_attempt_hint.get("1_2_1") == 3


async def _run_retry_task_clears_next_attempt_hint_on_reset(monkeypatch):
    runner = ExecutionRunner(sio=None, session_id="test")
    runner.idea_id = "idea_x"
    runner.plan_id = "plan_y"
    runner.is_running = True
    runner.task_map = {
        "1_1": {"task_id": "1_1", "dependencies": [], "status": "done"},
        "1_2_1": {"task_id": "1_2_1", "dependencies": ["1_1"], "status": "validation-failed"},
        "1_2_2": {"task_id": "1_2_2", "dependencies": ["1_2_1"], "status": "undone"},
    }
    runner.reverse_dependency_index = {
        "1_1": ["1_2_1"],
        "1_2_1": ["1_2_2"],
        "1_2_2": [],
    }
    runner.completed_tasks = {"1_1"}
    runner.pending_tasks = {"1_2_1", "1_2_2"}
    runner.running_tasks = set()
    runner.task_forced_attempt = {"1_2_1": 3, "1_2_2": 4}
    runner.task_next_attempt_hint = {"1_2_1": 3, "1_2_2": 4}

    from task_agent import runner as runner_mod

    monkeypatch.setitem(runner_mod.worker_manager, "release_worker_by_task_id", lambda _task_id: None)

    async def fake_delete_artifact(*_args, **_kwargs):
        return None

    async def fake_clear_memories(*_args, **_kwargs):
        return None

    monkeypatch.setattr(runner_mod, "delete_task_artifact", fake_delete_artifact)
    monkeypatch.setattr(runner_mod, "delete_task_attempt_memories", fake_clear_memories)

    ok = await runner.retry_task("1_2_1")
    assert ok is True
    assert "1_2_1" not in runner.task_next_attempt_hint
    assert "1_2_2" not in runner.task_next_attempt_hint


def test_retry_task_clears_next_attempt_hint_on_reset(monkeypatch):
    anyio.run(_run_retry_task_clears_next_attempt_hint_on_reset, monkeypatch)


async def _run_retry_sets_authoritative_run_attempt(monkeypatch):
    runner = ExecutionRunner(sio=None, session_id="test")
    runner.task_run_attempt["1_2_1"] = 1

    emitted = []

    def fake_emit(event, data):
        emitted.append((event, data))

    async def fake_append(_task_id, _event, _payload):
        return None

    from task_agent import runner as runner_mod

    monkeypatch.setitem(runner_mod.worker_manager, "release_worker_by_task_id", lambda _task_id: None)
    runner._emit = fake_emit
    runner._append_step_event = fake_append  # type: ignore[method-assign]
    runner._spawn_task_execution = lambda _task: None  # type: ignore[method-assign]

    await runner._retry_or_fail(
        task={"task_id": "1_2_1"},
        phase="validation",
        error="validation failed",
        decision={"action": "retry"},
    )

    assert runner.task_run_attempt.get("1_2_1") == 2
    retry_payload = next(data for event, data in emitted if event in ("attempt-retry", "task-retry"))
    assert retry_payload.get("nextAttempt") == 2


def test_retry_sets_authoritative_run_attempt(monkeypatch):
    anyio.run(_run_retry_sets_authoritative_run_attempt, monkeypatch)


async def _run_duplicate_retry_attempt_is_suppressed(monkeypatch):
    runner = ExecutionRunner(sio=None, session_id="test")
    runner.task_last_retry_attempt["1_2_1"] = 1

    emitted = []

    def fake_emit(event, data):
        emitted.append((event, data))

    async def fake_append(_task_id, _event, _payload):
        return None

    from task_agent import runner as runner_mod

    monkeypatch.setitem(runner_mod.worker_manager, "release_worker_by_task_id", lambda _task_id: None)
    runner._emit = fake_emit
    runner._append_step_event = fake_append  # type: ignore[method-assign]

    spawned = {"value": 0}

    def fake_spawn(_task):
        spawned["value"] += 1

    runner._spawn_task_execution = fake_spawn  # type: ignore[method-assign]

    await runner._retry_or_fail(
        task={"task_id": "1_2_1"},
        phase="validation",
        error="validation failed again",
        decision={"action": "retry"},
    )

    assert spawned["value"] == 0
    # Duplicate retry should be treated as terminal for this cycle.
    assert any(event == "task-error" and data.get("willRetry") is False for event, data in emitted)


def test_duplicate_retry_attempt_is_suppressed(monkeypatch):
    anyio.run(_run_duplicate_retry_attempt_is_suppressed, monkeypatch)


async def _run_retry_exhaustion_triggers_fail_fast(monkeypatch):
    runner = ExecutionRunner(sio=None, session_id="test")
    runner.is_running = True
    runner.MAX_RETRY_ATTEMPTS = 5
    runner.task_last_retry_attempt["1_2_1"] = 4
    runner.task_map = {
        "1_2_1": {"task_id": "1_2_1", "status": "validation-failed", "dependencies": []},
        "1_2_2": {"task_id": "1_2_2", "status": "undone", "dependencies": ["1_2_1"]},
    }
    runner.chain_cache = [runner.task_map["1_2_1"], runner.task_map["1_2_2"]]
    runner.reverse_dependency_index = {"1_2_1": ["1_2_2"], "1_2_2": []}
    runner.pending_tasks = {"1_2_1", "1_2_2"}
    runner.running_tasks = {"1_2_1"}

    emitted = []

    def fake_emit(event, data):
        emitted.append((event, data))

    async def fake_append(_task_id, _event, _payload):
        return None

    from task_agent import runner as runner_mod

    monkeypatch.setitem(runner_mod.worker_manager, "release_worker_by_task_id", lambda _task_id: None)
    runner._emit = fake_emit
    runner._append_step_event = fake_append  # type: ignore[method-assign]
    runner._broadcast_worker_states = lambda: None  # type: ignore[method-assign]
    runner._broadcast_task_states = lambda: None  # type: ignore[method-assign]
    runner._persist_execution = lambda: None  # type: ignore[method-assign]

    await runner._retry_or_fail(
        task={"task_id": "1_2_1"},
        phase="validation",
        error="validation failed max attempts",
        decision={"action": "retry"},
    )

    assert runner.is_running is False
    assert "1_2_1" not in runner.completed_tasks
    assert "1_2_2" in runner.pending_tasks
    fatal_events = [
        data
        for event, data in emitted
        if event == "task-error" and data.get("fatal") is True
    ]
    assert fatal_events, "Expected fatal task-error event when retry attempts are exhausted"


def test_retry_exhaustion_triggers_fail_fast(monkeypatch):
    anyio.run(_run_retry_exhaustion_triggers_fail_fast, monkeypatch)


async def _run_dependency_gap_stops_execution(monkeypatch):
    runner = ExecutionRunner(sio=None, session_id="test")
    runner.is_running = True
    runner.chain_cache = [
        {"task_id": "1_2", "dependencies": ["1_1"], "status": "undone"},
    ]
    runner.task_map = {
        "1_2": {"task_id": "1_2", "dependencies": ["1_1"], "status": "undone"},
    }
    runner.pending_tasks = {"1_2"}
    runner.completed_tasks = set()
    runner.running_tasks = set()

    emitted = []

    def fake_emit(event, data):
        emitted.append((event, data))

    runner._emit = fake_emit
    runner._persist_execution = lambda: None  # type: ignore[method-assign]
    runner._broadcast_task_states = lambda: None  # type: ignore[method-assign]
    runner._broadcast_worker_states = lambda: None  # type: ignore[method-assign]

    await runner._execute_tasks()

    assert runner.is_running is False
    fatal_events = [
        data for event, data in emitted
        if event == "task-error" and data.get("fatal") is True
    ]
    assert fatal_events, "Expected fatal task-error when dependency is in neither todo nor completed sets"
    assert "Dependency resolution gap" in str(fatal_events[-1].get("error") or "")


def test_dependency_gap_stops_execution(monkeypatch):
    anyio.run(_run_dependency_gap_stops_execution, monkeypatch)


async def _run_retry_can_spawn_next_attempt_from_inflight_task(monkeypatch):
    runner = ExecutionRunner(sio=None, session_id="test")
    runner.is_running = True

    emitted = []

    def fake_emit(event, data):
        emitted.append((event, data))

    async def fake_append(_task_id, _event, _payload):
        return None

    from task_agent import runner as runner_mod

    monkeypatch.setitem(runner_mod.worker_manager, "release_worker_by_task_id", lambda _task_id: None)
    runner._emit = fake_emit
    runner._append_step_event = fake_append  # type: ignore[method-assign]

    async def fake_execute_task(_task):
        await anyio.sleep(0.05)

    async def fake_handle_task_error(_task, _error):
        raise AssertionError("_handle_task_error should not be called in this test")

    runner._execute_task = fake_execute_task  # type: ignore[method-assign]
    runner._handle_task_error = fake_handle_task_error  # type: ignore[method-assign]

    async def trigger_retry_with_inflight_handle():
        current = asyncio.current_task()
        runner.task_tasks["1_2_1"] = asyncio.current_task()
        await runner._retry_or_fail(
            task={"task_id": "1_2_1"},
            phase="validation",
            error="validation failed",
            decision={"action": "retry"},
        )
        replacement = runner.task_tasks.get("1_2_1")
        assert replacement is not None
        assert replacement is not current
        assert replacement.done() is False

    await trigger_retry_with_inflight_handle()
    assert any(event in ("attempt-retry", "task-retry") for event, _ in emitted)

    spawned = runner.task_tasks.get("1_2_1")
    if spawned and not spawned.done():
        spawned.cancel()


def test_retry_can_spawn_next_attempt_from_inflight_task(monkeypatch):
    anyio.run(_run_retry_can_spawn_next_attempt_from_inflight_task, monkeypatch)


def test_reserve_execute_attempt_is_monotonic_per_task():
    runner = ExecutionRunner(sio=None, session_id="test")

    a1 = runner._reserve_execute_attempt("1_2_1", 1)
    a2 = runner._reserve_execute_attempt("1_2_1", 1)
    a3 = runner._reserve_execute_attempt("1_2_1", 2)

    assert a1 == 1
    assert a2 == 2
    assert a3 == 3


def test_step_a_structural_gate_fails_on_empty_output():
    passed, report = ExecutionRunner._run_step_a_structural_format_gate(
        "   ",
        {"format": "text"},
    )
    assert passed is False
    assert "FAIL" in report


def test_step_a_structural_gate_requires_json_parse_when_expected():
    passed, report = ExecutionRunner._run_step_a_structural_format_gate(
        "not json",
        {"format": "JSON"},
    )
    assert passed is False
    assert "parsing failed" in report


def test_step_a_structural_gate_passes_semantic_content_if_structure_ok():
    # Step A should only care about structure, not whether content is acceptable.
    passed, report = ExecutionRunner._run_step_a_structural_format_gate(
        {"answer": "wrong but structured"},
        {"format": "JSON"},
    )
    assert passed is True
    assert "PASS" in report
