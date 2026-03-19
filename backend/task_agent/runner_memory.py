"""Attempt-memory and execution-context helper functions for Task ExecutionRunner.

All functions are stateless module-level functions. State dictionaries
and dep callables are passed explicitly.
"""

import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from loguru import logger


async def record_task_attempt_failure(
    task_attempt_history: Dict[str, List[Dict[str, Any]]],
    research_id: str,
    save_fn: Callable[..., Awaitable[Any]],
    *,
    task_id: str,
    phase: str,
    attempt: int,
    error: str,
    will_retry: bool,
    decision: Optional[Dict[str, Any]] = None,
) -> None:
    decision = decision or {}
    history = task_attempt_history.setdefault(task_id, [])
    history.append({
        "attempt": attempt,
        "phase": phase,
        "error": (error or "").strip(),
        "willRetry": bool(will_retry),
        "decision": str(decision.get("action") or ""),
        "category": str(decision.get("category") or ""),
        "summary": str(decision.get("summary") or ""),
        "ts": int(time.time() * 1000),
    })
    if len(history) > 8:
        task_attempt_history[task_id] = history[-8:]
    if research_id:
        latest = task_attempt_history.get(task_id, [])[-1]
        await save_fn(
            research_id,
            task_id,
            int(attempt),
            {
                "attempt": int(attempt),
                "phase": phase,
                "error": latest.get("error") or "",
                "willRetry": bool(will_retry),
                "decision": latest.get("decision") or "",
                "category": latest.get("category") or "",
                "summary": latest.get("summary") or "",
                "ts": latest.get("ts"),
            },
        )


async def load_task_attempt_memories(
    task_attempt_history: Dict[str, List[Dict[str, Any]]],
    research_id: str,
    list_fn: Callable[..., Awaitable[List]],
) -> None:
    task_attempt_history.clear()
    if not research_id:
        return
    try:
        rows = await list_fn(research_id)
    except Exception:
        logger.exception("Failed to load task attempt memories research_id={}", research_id)
        return
    grouped: Dict[str, list[Dict[str, Any]]] = {}
    for row in rows or []:
        task_id = str(row.get("taskId") or "").strip()
        if not task_id:
            continue
        data = row.get("data") or {}
        grouped.setdefault(task_id, []).append(
            {
                "attempt": int(data.get("attempt") or row.get("attempt") or 0),
                "phase": str(data.get("phase") or "execution"),
                "error": str(data.get("error") or ""),
                "willRetry": bool(data.get("willRetry")),
                "decision": str(data.get("decision") or ""),
                "category": str(data.get("category") or ""),
                "summary": str(data.get("summary") or ""),
                "ts": int(data.get("ts") or 0),
            }
        )
    for task_id, items in grouped.items():
        task_attempt_history[task_id] = sorted(items, key=lambda x: (x.get("attempt") or 0, x.get("ts") or 0))[-8:]


async def clear_attempt_history_for_tasks(
    task_attempt_history: Dict[str, List[Dict[str, Any]]],
    research_id: str,
    delete_fn: Callable[..., Awaitable[Any]],
    task_ids: Set[str],
) -> None:
    for task_id in set(task_ids or set()):
        task_attempt_history.pop(task_id, None)
        if research_id:
            try:
                await delete_fn(research_id, task_id)
            except Exception:
                logger.exception("Failed to clear task attempt memories research_id={} task_id={}", research_id, task_id)


def build_task_execution_context(
    *,
    task: Dict[str, Any],
    resolved_inputs: Dict[str, Any],
    completed_tasks: Set[str],
    task_attempt_history: Dict[str, List[Dict[str, Any]]],
    chain_cache: List[Dict],
    idea_text: str,
    execution_run_id: str,
) -> Dict[str, Any]:
    task_id = task.get("task_id") or ""
    deps = task.get("dependencies") or []
    completed = sorted([tid for tid in completed_tasks if tid in set(deps)])
    pending = sorted([tid for tid in deps if tid not in completed_tasks])
    history = task_attempt_history.get(task_id, [])
    latest_failure = history[-1] if history else None

    done_count = 0
    running_count = 0
    failed_count = 0
    for t in chain_cache:
        status = str((t or {}).get("status") or "undone")
        if status == "done":
            done_count += 1
        elif status == "doing":
            running_count += 1
        elif status in ("execution-failed", "validation-failed"):
            failed_count += 1

    output_spec = task.get("output") or {}
    validation_spec = task.get("validation") or {}
    input_keys = sorted(list((resolved_inputs or {}).keys())) if isinstance(resolved_inputs, dict) else []

    context: Dict[str, Any] = {
        "globalGoal": (idea_text or "").strip(),
        "planContext": {
            "executionRunId": execution_run_id,
            "currentTaskId": task_id,
            "progress": {
                "done": done_count,
                "running": running_count,
                "failed": failed_count,
                "total": len(chain_cache),
            },
            "dependencies": {
                "all": deps,
                "completed": completed,
                "pending": pending,
            },
        },
        "taskContract": {
            "description": task.get("description") or "",
            "inputKeys": input_keys,
            "outputFormat": output_spec.get("format") or "",
            "outputDescription": output_spec.get("description") or "",
            "validationCriteria": (validation_spec.get("criteria") or []) if isinstance(validation_spec, dict) else [],
        },
    }

    if latest_failure:
        context["retryMemory"] = {
            "attempt": latest_failure.get("attempt"),
            "phase": latest_failure.get("phase") or "execution",
            "lastFailure": latest_failure.get("error") or "",
            "historyCount": len(history),
            "doNext": [
                "Reuse existing files and artifacts before creating new ones",
                "Take the shortest path to produce required output and call Finish",
            ],
            "dontNext": [
                "Do not repeat identical failing commands without a change",
                "Do not keep exploring once output spec is satisfied",
            ],
        }

    return context
