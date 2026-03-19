"""Execution-phase orchestration helper functions for Task ExecutionRunner."""

import asyncio
import time
from typing import Any, Dict, List, Optional

from loguru import logger


def find_dependency_gap(runner) -> Optional[Dict[str, str]]:
    """Find a task waiting on a dependency that is in neither todo nor completed sets."""
    todo_ids = set(runner.pending_tasks) | set(runner.running_tasks)
    completed_ids = set(runner.completed_tasks)
    for task in runner.chain_cache:
        task_id = str(task.get("task_id") or "")
        if not task_id or task_id in completed_ids:
            continue
        for dep_id in task.get("dependencies") or []:
            dep = str(dep_id or "").strip()
            if not dep:
                continue
            if dep in completed_ids or dep in todo_ids:
                continue
            return {
                "taskId": task_id,
                "dependencyId": dep,
            }
    return None


async def run_step_b_contract_review(
    runner,
    *,
    task: Dict[str, Any],
    result: Any,
    reason: str,
    output_format: str,
    on_thinking: Optional[Any] = None,
) -> Dict[str, Any]:

    task_id = str(task.get("task_id") or "")
    validation = task.setdefault("validation", {})
    if not isinstance(validation, dict):
        validation = {}
        task["validation"] = validation
    original = runner._get_original_validation_criteria(task)
    active = list(validation.get("criteria") or [])

    packet = {
        "task": {
            "taskId": task_id,
            "description": task.get("description") or "",
            "outputFormat": output_format or "",
        },
        "globalGoal": runner._idea_text or "",
        "attemptHistory": list(runner.task_attempt_history.get(task_id) or []),
        "initialValidationCriteria": original,
        "activeValidationCriteria": active,
        "resultPreview": (result if isinstance(result, dict) else {"content": str(result)[:800]}),
        "failureReason": reason or "",
        "immutableItems": validation.get("immutableItems") or [],
    }

    if (runner.api_config or {}).get("taskUseMock"):
        return {
            "shouldAdjust": False,
            "immutableImpacted": False,
            "reasoning": "Mock mode: Step-B review skipped.",
            "proposedValidationCriteria": active,
            "patchSummary": "",
            "source": "step-b-agent",
        }

    try:
        reviewed = await runner._deps.review_contract_adjustment(
            packet,
            api_config=runner.api_config,
            abort_event=runner.abort_event,
            on_thinking=on_thinking,
        )
    except Exception as exc:
        logger.warning("Step-B contract review failed task_id={} error={}", task_id, exc)
        return {
            "shouldAdjust": False,
            "immutableImpacted": False,
            "reasoning": f"Step-B review failed: {exc}",
            "proposedValidationCriteria": active,
            "patchSummary": "",
            "source": "step-b-agent",
        }

    if reviewed.get("shouldAdjust") and not reviewed.get("immutableImpacted"):
        proposed = list(reviewed.get("proposedValidationCriteria") or [])
        if proposed:
            validation["criteria"] = proposed
    return reviewed


async def retry_or_fail(
    runner,
    *,
    task: Dict[str, Any],
    phase: str,
    error: str,
    decision: Optional[Dict[str, Any]] = None,
) -> None:

    task_id = str(task.get("task_id") or "")
    attempt = runner._next_retry_attempt(task_id)
    last_retry_attempt = int(runner.task_last_retry_attempt.get(task_id) or 0)
    duplicate_retry_attempt = attempt <= last_retry_attempt
    will_retry = attempt < runner.MAX_RETRY_ATTEMPTS and not duplicate_retry_attempt

    payload = {
        "taskId": task_id,
        "phase": phase,
        "attempt": attempt,
        "maxAttempts": runner.MAX_RETRY_ATTEMPTS,
        "willRetry": will_retry,
        "error": error,
        "decision": decision or {},
    }
    runner._emit("task-error", payload)
    await runner._record_task_attempt_failure(
        task_id=task_id,
        phase=phase,
        attempt=attempt,
        will_retry=will_retry,
        error=error,
        decision=decision,
    )
    await runner._append_step_event(task_id, "task-error", payload)

    async with runner._worker_lock:
        runner._deps.release_worker(task_id)
    runner._broadcast_worker_states()

    runner.running_tasks.discard(task_id)

    if not will_retry:
        runner.pending_tasks.discard(task_id)
        runner._update_task_status(task_id, "failed")
        await runner._trigger_fail_fast(
            failed_task_id=task_id,
            phase=phase,
            reason=error,
        )
        return

    runner.task_last_retry_attempt[task_id] = attempt
    next_attempt = attempt + 1
    runner.task_run_attempt[task_id] = next_attempt
    runner.task_forced_attempt[task_id] = next_attempt
    runner.task_next_attempt_hint[task_id] = max(int(runner.task_next_attempt_hint.get(task_id) or 0), next_attempt)

    runner.pending_tasks.add(task_id)
    runner._update_task_status(task_id, "undone")

    retry_payload = {
        "taskId": task_id,
        "phase": phase,
        "attempt": attempt,
        "nextAttempt": next_attempt,
        "maxAttempts": runner.MAX_RETRY_ATTEMPTS,
        "error": error,
        "decision": decision or {},
    }
    runner._emit("attempt-retry", retry_payload)
    await runner._append_step_event(task_id, "attempt-retry", retry_payload)

    runner._spawn_task_execution(task)


def get_ready_tasks(runner) -> List[Dict]:
    ready: List[Dict] = []
    for task in runner.chain_cache:
        task_id = task["task_id"]
        if task_id in runner.completed_tasks or task_id in runner.running_tasks:
            continue
        if task_id not in runner.pending_tasks:
            continue
        if runner._are_dependencies_satisfied(task):
            ready.append(task)
    return ready


async def execute_tasks(runner) -> None:
    runner.is_running = True

    initial_ready = get_ready_tasks(runner)
    logger.info(
        "Execution scheduling start idea_id={} plan_id={} initial_ready={} total={} ready_ids={}",
        runner.idea_id,
        runner.plan_id,
        len(initial_ready),
        len(runner.chain_cache),
        [t.get("task_id") for t in initial_ready],
    )
    for task in initial_ready:
        runner._spawn_task_execution(task)

    last_heartbeat = time.monotonic()
    while runner.is_running and (len(runner.completed_tasks) < len(runner.chain_cache) or len(runner.running_tasks) > 0):
        dependency_gap = find_dependency_gap(runner)
        if dependency_gap:
            await runner._trigger_fail_fast(
                failed_task_id=dependency_gap.get("taskId") or "unknown",
                phase="dependency",
                reason=(
                    "Dependency resolution gap: dependency "
                    f"{dependency_gap.get('dependencyId')} for task "
                    f"{dependency_gap.get('taskId')} is in neither todo nor completed lists"
                ),
            )
            break

        ready = get_ready_tasks(runner)
        for task in ready:
            runner._spawn_task_execution(task)

        now = time.monotonic()
        if now - last_heartbeat >= 5:
            logger.info(
                "Execution heartbeat idea_id={} plan_id={} completed={} running={} pending={} running_ids={} pending_ids={}",
                runner.idea_id,
                runner.plan_id,
                len(runner.completed_tasks),
                len(runner.running_tasks),
                len(runner.pending_tasks),
                sorted(runner.running_tasks),
                sorted(list(runner.pending_tasks))[:12],
            )
            last_heartbeat = now
        await asyncio.sleep(0.1)

    logger.info(
        "Final state: {}/{} tasks completed",
        len(runner.completed_tasks),
        len(runner.chain_cache),
    )
    if runner.is_running:
        runner._emit("task-complete", {"completed": len(runner.completed_tasks), "total": len(runner.chain_cache)})
    else:
        runner._emit("task-error", {"error": "Task execution stopped by user"})
