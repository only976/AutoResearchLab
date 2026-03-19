"""Execution runner state/scheduling/rollback helper functions.

Functions are either pure (explicit params) or take a runner instance
as the first argument, eliminating mixin inheritance while keeping code
organized in a separate module.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from db import get_execution_task_step_dir


# ---- Pure functions (no runner needed) ----

def are_dependencies_satisfied(completed_tasks: Set[str], task: Dict) -> bool:
    deps = task.get("dependencies") or []
    if not deps:
        return True
    return all(d in completed_tasks for d in deps)


def append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


async def append_step_event(execution_run_id: str, task_id: str, event: str, payload: Dict[str, Any]) -> None:
    if not execution_run_id or not task_id:
        return
    try:
        step_dir = get_execution_task_step_dir(execution_run_id, task_id).resolve()
        step_dir.mkdir(parents=True, exist_ok=True)
        path = step_dir / "events.jsonl"
        record = {
            "ts": int(time.time() * 1000),
            "runId": execution_run_id,
            "taskId": task_id,
            "event": event,
            "payload": payload or {},
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        await asyncio.to_thread(append_line, path, line)
    except Exception as e:
        logger.debug("Failed to append step event task_id={} event={} error={}", task_id, event, e)


# ---- Functions that operate on runner state ----

def schedule_ready_tasks(runner, tasks_to_check: List[Dict]) -> None:
    if not tasks_to_check or not runner.is_running:
        return
    ready = [
        t for t in tasks_to_check
        if t and t["task_id"] not in runner.completed_tasks
        and t["task_id"] not in runner.running_tasks
        and t["task_id"] in runner.pending_tasks
        and runner._are_dependencies_satisfied(t)
    ]
    for task in ready:
        runner._spawn_task_execution(task)


async def handle_task_error(runner, task: Dict, error: Exception) -> None:
    logger.exception("Error executing task %s", task["task_id"])
    runner._emit("task-error", {
        "taskId": task["task_id"],
        "phase": "execution",
        "willRetry": False,
        "error": str(error),
    })
    async with runner._worker_lock:
        runner._deps.release_worker(task["task_id"])
    runner._broadcast_worker_states()
    runner.running_tasks.discard(task["task_id"])
    runner.pending_tasks.discard(task["task_id"])
    runner._update_task_status(task["task_id"], "execution-failed")
    await runner._trigger_fail_fast(
        failed_task_id=task["task_id"],
        phase="execution",
        reason=str(error),
    )


async def trigger_fail_fast(runner, *, failed_task_id: str, phase: str, reason: str) -> None:
    if not runner.is_running:
        return

    runner.is_running = False
    if runner.abort_event:
        runner.abort_event.set()

    runner._emit("task-error", {
        "taskId": failed_task_id,
        "phase": phase,
        "willRetry": False,
        "error": reason or "Task failed",
        "fatal": True,
    })

    for tid, asyncio_task in list(runner.task_tasks.items()):
        if tid == failed_task_id:
            continue
        if asyncio_task and not asyncio_task.done():
            asyncio_task.cancel()

    for tid in list(runner.running_tasks):
        if tid == failed_task_id:
            continue
        runner.running_tasks.discard(tid)
        runner.pending_tasks.discard(tid)
        runner._update_task_status(tid, "stopped")

    runner._broadcast_worker_states()


def update_task_status(runner, task_id: str, status: str) -> None:
    t = runner.task_map.get(task_id)
    if t:
        t["status"] = status
    try:
        asyncio.create_task(runner._append_step_event(task_id, "task-status", {"status": status}))
    except RuntimeError:
        pass
    runner._persist_execution()
    runner._broadcast_task_states()


async def stop_all_task_containers(runner) -> None:
    containers = list(runner.task_docker_containers.values())
    runner.task_docker_containers.clear()
    for container_name in containers:
        try:
            await runner._deps.stop_execution_container(container_name)
        except Exception:
            logger.exception("Failed to stop Docker execution container {}", container_name)
    runner.docker_container_name = ""


def broadcast_task_states(runner) -> None:
    task_states = [{"task_id": t["task_id"], "status": t["status"]} for t in runner.chain_cache]
    runner._emit("task-states-update", {"tasks": task_states})


def broadcast_worker_states(runner) -> None:
    """Broadcast execution concurrency stats. (Frontend uses syncExecutionStateOnConnect for stats.)"""


async def rollback_task(runner, task: Dict) -> None:
    tasks_to_rollback: Set[str] = set()
    tasks_to_rollback.add(task["task_id"])

    visited: Set[str] = set()

    def find_downstream(tid: str) -> None:
        if tid in visited:
            return
        visited.add(tid)
        for dep_id in runner.reverse_dependency_index.get(tid, []):
            if dep_id not in tasks_to_rollback:
                tasks_to_rollback.add(dep_id)
                find_downstream(dep_id)

    find_downstream(task["task_id"])

    async with runner._worker_lock:
        for task_id in tasks_to_rollback:
            t = runner.task_map.get(task_id)
            if t:
                runner.completed_tasks.discard(task_id)
                runner.pending_tasks.add(task_id)
                runner.running_tasks.discard(task_id)
                runner._update_task_status(task_id, "undone")
                runner._clear_task_failure_counts(task_id)
                runner.task_last_retry_attempt.pop(task_id, None)
                runner.task_run_attempt.pop(task_id, None)
                runner.task_forced_attempt.pop(task_id, None)
                runner.task_next_attempt_hint.pop(task_id, None)
                runner.task_execute_started_attempts.pop(task_id, None)
                runner.task_tasks.pop(task_id, None)
                runner._deps.release_worker(task_id)
            if runner.idea_id and runner.plan_id:
                await runner._deps.delete_task_artifact(runner.idea_id, runner.plan_id, task_id)

    runner._broadcast_worker_states()

    ready = [
        runner.task_map[tid]
        for tid in tasks_to_rollback
        if runner.task_map.get(tid)
        and runner._are_dependencies_satisfied(runner.task_map[tid])
        and tid in runner.pending_tasks
    ]
    if ready:
        runner._schedule_ready_tasks(ready)


def set_layout(
    runner,
    layout: Dict,
    idea_id: Optional[str] = None,
    plan_id: Optional[str] = None,
    execution: Optional[Dict] = None,
) -> None:
    if runner.is_running:
        raise ValueError("Cannot set layout while execution is running")
    runner.execution_layout = layout
    runner.idea_id = idea_id
    runner.plan_id = plan_id
    runner.chain_cache = []
    task_by_id = {}
    if execution:
        for t in execution.get("tasks") or []:
            if t.get("task_id"):
                task_by_id[t["task_id"]] = t
    for t in layout.get("treeData") or []:
        if t and t.get("task_id"):
            tid = t["task_id"]
            full = task_by_id.get(tid, {})
            status = full.get("status") or t.get("status") or "undone"
            runner.chain_cache.append({
                "task_id": tid,
                "title": full.get("title") or t.get("title"),
                "dependencies": t.get("dependencies") or [],
                "status": status,
                "description": full.get("description") or t.get("description"),
                "input": full.get("input") or t.get("input"),
                "output": full.get("output") or t.get("output"),
                "validation": full.get("validation") or t.get("validation"),
            })


async def retry_task(runner, task_id: str) -> bool:
    if task_id not in runner.task_map:
        return False
    tasks_to_reset = runner._get_downstream_task_ids(task_id)

    for tid in list(tasks_to_reset):
        asyncio_task = runner.task_tasks.pop(tid, None)
        if asyncio_task and not asyncio_task.done():
            asyncio_task.cancel()

    async with runner._worker_lock:
        for tid in tasks_to_reset:
            runner.completed_tasks.discard(tid)
            runner.running_tasks.discard(tid)
            runner.pending_tasks.add(tid)
            runner._clear_task_failure_counts(tid)
            runner.task_last_retry_attempt.pop(tid, None)
            runner.task_run_attempt.pop(tid, None)
            runner.task_forced_attempt.pop(tid, None)
            runner.task_next_attempt_hint.pop(tid, None)
            if not runner.is_running:
                runner.task_execute_started_attempts.pop(tid, None)
            if tid in runner.task_map:
                runner.task_map[tid]["status"] = "undone"
            runner._deps.release_worker(tid)
            if runner.idea_id and runner.plan_id:
                await runner._deps.delete_task_artifact(runner.idea_id, runner.plan_id, tid)

    await runner._clear_attempt_history_for_tasks(tasks_to_reset)

    runner._persist_execution()
    runner._broadcast_task_states()
    runner._broadcast_worker_states()

    if runner.is_running:
        ready = [
            runner.task_map[tid]
            for tid in tasks_to_reset
            if tid in runner.task_map
            and tid in runner.pending_tasks
            and runner._are_dependencies_satisfied(runner.task_map[tid])
        ]
        if ready:
            runner._schedule_ready_tasks(ready)
    return True


async def stop_async(runner) -> None:
    runner.is_running = False
    if runner.abort_event:
        runner.abort_event.set()
    runner._emit("task-error", {"error": "Task execution stopped by user"})
    task_ids = list(runner.task_tasks.keys())
    for task_id in task_ids:
        asyncio_task = runner.task_tasks.get(task_id)
        if asyncio_task and not asyncio_task.done():
            asyncio_task.cancel()
    async with runner._worker_lock:
        for task_id in task_ids:
            runner._deps.release_worker(task_id)
    runner.task_tasks.clear()
    runner.running_tasks.clear()
    await runner._stop_all_task_containers()
    runner.docker_runtime_status = await runner._deps.get_local_docker_status(enabled=bool((runner.api_config or {}).get("taskAgentMode")))
    runner._emit_runtime_status()
    runner._broadcast_worker_states()
