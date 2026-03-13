"""
Task Agent 实现 - Execution 阶段编排器，管理 worker pool。
Task Agent 含两阶段：Execution（执行原子任务）→ Validation（验证产出）。每个 task 依次经历两阶段。
单轮 LLM 在 task_agent/llm/。
"""

import asyncio
import json
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from db import DB_DIR, delete_task_artifact, get_execution_task_step_dir, get_idea, save_execution, save_task_artifact, save_validation_report
from db import delete_task_attempt_memories, list_task_attempt_memories, save_task_attempt_memory
from shared.constants import (
    MAX_EXECUTION_CONCURRENCY,
    MAX_FAILURES,
    MOCK_EXECUTION_PASS_PROBABILITY,
    MOCK_VALIDATION_PASS_PROBABILITY,
)
from shared.idea_utils import get_idea_text
from shared.utils import chunk_string
from .pools import worker_manager
from .artifact_resolver import resolve_artifacts
from .agent import run_task_agent
from .agent_tools import SKILLS_ROOT
from .docker_runtime import ensure_execution_container, get_local_docker_status, prepare_execution_runtime, stop_execution_container
from .llm.executor import execute_task
from .llm.validation import validate_task_output_with_llm
from shared.reflection import self_evaluate, generate_skill_from_reflection, save_learned_skill


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


_MOCK_VALIDATOR_CHUNK_DELAY = _env_float("MAARS_MOCK_VALIDATOR_CHUNK_DELAY", 0.03)


class ExecutionRunner:
    def __init__(self, sio: Any, session_id: Optional[str] = None):
        self.sio = sio
        self.session_id = session_id
        self._worker_lock = asyncio.Lock()
        self.is_running = False
        self.running_tasks: Set[str] = set()
        self.completed_tasks: Set[str] = set()
        self.pending_tasks: Set[str] = set()
        self.task_tasks: Dict[str, asyncio.Task] = {}
        self.chain_cache: List[Dict] = []
        self.task_map: Dict[str, Dict] = {}
        self.reverse_dependency_index: Dict[str, List[str]] = {}
        self.task_failure_count: Dict[str, int] = {}
        self.EXECUTION_PASS_PROBABILITY = MOCK_EXECUTION_PASS_PROBABILITY
        self.VALIDATION_PASS_PROBABILITY = MOCK_VALIDATION_PASS_PROBABILITY
        self.MAX_FAILURES = MAX_FAILURES
        self.execution_layout = None
        self.idea_id: Optional[str] = None
        self.plan_id: Optional[str] = None
        self.api_config: Optional[Dict] = None
        self.abort_event: Optional[asyncio.Event] = None
        self._idea_text: str = ""
        self._persist_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self.execution_run_id: str = ""
        self.docker_container_name: str = ""
        self.task_docker_containers: Dict[str, str] = {}
        self.docker_runtime_status: Dict[str, Any] = {"enabled": False, "available": False, "connected": False}
        self.task_attempt_history: Dict[str, List[Dict[str, Any]]] = {}
        self.research_id: str = ""

    def _emit_runtime_status(self) -> None:
        payload = dict(self.docker_runtime_status or {})
        payload["executionRunId"] = self.execution_run_id
        payload["ideaId"] = self.idea_id or ""
        payload["planId"] = self.plan_id or ""
        self._emit("execution-runtime-status", payload)

    def _persist_execution(self) -> None:
        """Persist chain_cache to execution.json. Serialized via _persist_lock to avoid concurrent write races."""
        if self.idea_id and self.plan_id and self.chain_cache:
            try:
                asyncio.create_task(self._persist_execution_async())
            except RuntimeError:
                pass

    async def _persist_execution_async(self) -> None:
        """Serialized persist: prevents multiple save_execution from overwriting each other with stale data."""
        async with self._persist_lock:
            if self.idea_id and self.plan_id and self.chain_cache:
                try:
                    await save_execution({"tasks": list(self.chain_cache)}, self.idea_id, self.plan_id)
                except Exception as e:
                    logger.warning("Failed to persist execution: %s", e)

    def _emit(self, event: str, data: dict) -> None:
        """Emit event to all clients (fire-and-forget)."""
        if hasattr(self.sio, "emit"):
            try:
                asyncio.create_task(self.sio.emit(event, data, to=self.session_id))
            except RuntimeError:
                pass

    async def _emit_await(self, event: str, data: dict) -> None:
        """Emit event and await; use for order-sensitive events (e.g. thinking chunks)."""
        if hasattr(self.sio, "emit"):
            try:
                await self.sio.emit(event, data, to=self.session_id)
            except Exception as e:
                logger.warning("%s emit failed: %s", event, e)

    def _get_downstream_task_ids(self, task_id: str) -> Set[str]:
        """Return task_id and all downstream dependents."""
        result: Set[str] = {task_id}
        visited: Set[str] = set()

        def collect(tid: str) -> None:
            if tid in visited:
                return
            visited.add(tid)
            result.add(tid)
            for dep_id in self.reverse_dependency_index.get(tid, []):
                collect(dep_id)

        collect(task_id)
        return result

    async def _record_task_attempt_failure(
        self,
        *,
        task_id: str,
        phase: str,
        attempt: int,
        error: str,
        will_retry: bool,
    ) -> None:
        history = self.task_attempt_history.setdefault(task_id, [])
        history.append({
            "attempt": attempt,
            "phase": phase,
            "error": (error or "").strip(),
            "willRetry": bool(will_retry),
            "ts": int(time.time() * 1000),
        })
        if len(history) > 8:
            self.task_attempt_history[task_id] = history[-8:]
        if self.research_id:
            latest = self.task_attempt_history.get(task_id, [])[-1]
            await save_task_attempt_memory(
                self.research_id,
                task_id,
                int(attempt),
                {
                    "attempt": int(attempt),
                    "phase": phase,
                    "error": latest.get("error") or "",
                    "willRetry": bool(will_retry),
                    "ts": latest.get("ts"),
                },
            )

    async def _load_task_attempt_memories(self) -> None:
        self.task_attempt_history.clear()
        if not self.research_id:
            return
        try:
            rows = await list_task_attempt_memories(self.research_id)
        except Exception:
            logger.exception("Failed to load task attempt memories research_id={}", self.research_id)
            return
        grouped: Dict[str, List[Dict[str, Any]]] = {}
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
                    "ts": int(data.get("ts") or 0),
                }
            )
        for task_id, items in grouped.items():
            self.task_attempt_history[task_id] = sorted(items, key=lambda x: (x.get("attempt") or 0, x.get("ts") or 0))[-8:]

    def _build_task_execution_context(
        self,
        task: Dict[str, Any],
        resolved_inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        task_id = task.get("task_id") or ""
        deps = task.get("dependencies") or []
        completed = sorted([tid for tid in self.completed_tasks if tid in set(deps)])
        pending = sorted([tid for tid in deps if tid not in self.completed_tasks])
        history = self.task_attempt_history.get(task_id, [])
        latest_failure = history[-1] if history else None

        done_count = 0
        running_count = 0
        failed_count = 0
        for t in self.chain_cache:
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
            "globalGoal": (self._idea_text or "").strip(),
            "planContext": {
                "executionRunId": self.execution_run_id,
                "currentTaskId": task_id,
                "progress": {
                    "done": done_count,
                    "running": running_count,
                    "failed": failed_count,
                    "total": len(self.chain_cache),
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

    async def start_execution(
        self,
        api_config: Optional[Dict] = None,
        resume_from_task_id: Optional[str] = None,
        research_id: Optional[str] = None,
    ) -> None:
        if api_config is not None:
            self.api_config = api_config
        async with self._start_lock:
            if self.is_running:
                raise ValueError("Execution is already running")
            if not self.chain_cache:
                raise ValueError("No execution map cache found. Please generate map first.")
            if not self.execution_layout:
                raise ValueError("No execution layout cache found. Please generate layout first.")
            self.is_running = True
        self.abort_event = asyncio.Event()
        self.research_id = str(research_id or self.research_id or "").strip()
        self._idea_text = ""
        self.execution_run_id = f"exec_{int(time.time() * 1000)}"
        self.docker_container_name = ""
        self.task_docker_containers.clear()
        self.docker_runtime_status = {"enabled": False, "available": False, "connected": False}
        if self.idea_id:
            try:
                idea_data = await get_idea(self.idea_id)
                if idea_data:
                    refined = idea_data.get("refined_idea")
                    self._idea_text = get_idea_text(refined) or (idea_data.get("idea") or "").strip()
            except Exception:
                pass
        try:
            max_conc = MAX_EXECUTION_CONCURRENCY
            worker_manager["initialize_workers"](max_conc)
            self._broadcast_worker_states()

            api_cfg = self.api_config or {}
            docker_enabled = bool(api_cfg.get("taskAgentMode"))
            if docker_enabled:
                self.docker_runtime_status = await prepare_execution_runtime(
                    enabled=True,
                    image=api_cfg.get("taskDockerImage"),
                )
            else:
                self.docker_runtime_status = await get_local_docker_status(enabled=False)
            self._emit_runtime_status()

            execution_layout = self.execution_layout
            self.running_tasks.clear()
            self.completed_tasks.clear()
            self.pending_tasks.clear()
            self.task_tasks.clear()
            self.task_map.clear()
            self.reverse_dependency_index.clear()
            self.task_failure_count.clear()
            await self._load_task_attempt_memories()

            for task in self.chain_cache:
                self.task_map[task["task_id"]] = task
                self.pending_tasks.add(task["task_id"])
                self.reverse_dependency_index[task["task_id"]] = []

            for task in self.chain_cache:
                for dep_id in (task.get("dependencies") or []):
                    if dep_id in self.reverse_dependency_index:
                        self.reverse_dependency_index[dep_id].append(task["task_id"])

            if resume_from_task_id and resume_from_task_id in self.task_map:
                to_reset = self._get_downstream_task_ids(resume_from_task_id)
                for task in self.chain_cache:
                    if task["task_id"] in to_reset:
                        task["status"] = "undone"
                        if self.idea_id and self.plan_id:
                            await delete_task_artifact(self.idea_id, self.plan_id, task["task_id"])
                        self.pending_tasks.add(task["task_id"])
                        self.completed_tasks.discard(task["task_id"])
                        self.task_failure_count.pop(task["task_id"], None)
                    elif task.get("status") == "done":
                        self.completed_tasks.add(task["task_id"])
                        self.pending_tasks.discard(task["task_id"])
            else:
                for task in self.chain_cache:
                    task["status"] = "undone"
            if self.idea_id and self.plan_id and self.chain_cache:
                await save_execution({"tasks": self.chain_cache}, self.idea_id, self.plan_id)

            self._emit("task-start", {})
            self._emit("execution-layout", {"layout": execution_layout})
            self._broadcast_task_states()
            await self._execute_tasks()
        except Exception as e:
            logger.exception("Error in execution")
            self._emit("task-error", {"error": str(e)})
            raise
        finally:
            self.is_running = False
            await self._stop_all_task_containers()
            self.docker_runtime_status = await get_local_docker_status(enabled=bool((self.api_config or {}).get("taskAgentMode")))
            self._emit_runtime_status()
            worker_manager["initialize_workers"]()
            self._broadcast_worker_states()

    def _get_ready_tasks(self) -> List[Dict]:
        result = []
        for task_id in self.pending_tasks:
            if task_id in self.running_tasks or task_id in self.completed_tasks:
                continue
            task = self.task_map.get(task_id)
            if task and self._are_dependencies_satisfied(task):
                result.append(task)
        return result

    async def _execute_tasks(self) -> None:
        initial_ready = self._get_ready_tasks()
        logger.info(
            "Execution start idea_id={} plan_id={} initial_ready={} total_tasks={} ready_ids={}",
            self.idea_id,
            self.plan_id,
            len(initial_ready),
            len(self.chain_cache),
            [t.get("task_id") for t in initial_ready],
        )

        for task in initial_ready:
            async def run_with_error_handling(t=task):
                try:
                    await self._execute_task(t)
                except Exception as e:
                    await self._handle_task_error(t, e)

            self.task_tasks[task["task_id"]] = asyncio.create_task(run_with_error_handling())

        # Event-driven: wait for completion (task completion triggers _schedule_ready_tasks)
        last_heartbeat = time.monotonic()
        while self.is_running and (len(self.completed_tasks) < len(self.chain_cache) or len(self.running_tasks) > 0):
            now = time.monotonic()
            if now - last_heartbeat >= 5:
                logger.info(
                    "Execution heartbeat idea_id={} plan_id={} completed={} running={} pending={} running_ids={} pending_ids={}",
                    self.idea_id,
                    self.plan_id,
                    len(self.completed_tasks),
                    len(self.running_tasks),
                    len(self.pending_tasks),
                    sorted(self.running_tasks),
                    sorted(list(self.pending_tasks))[:12],
                )
                last_heartbeat = now
            await asyncio.sleep(0.1)

        logger.info(
            "Final state: {}/{} tasks completed",
            len(self.completed_tasks),
            len(self.chain_cache),
        )
        if self.is_running:
            self._emit("task-complete", {"completed": len(self.completed_tasks), "total": len(self.chain_cache)})
        else:
            self._emit("task-error", {"error": "Task execution stopped by user"})

    async def _execute_task(self, task: Dict) -> None:
        if not self.is_running:
            return
        logger.info(
            "Task start task_id={} deps={} status={} running={} completed={} pending={}",
            task.get("task_id"),
            task.get("dependencies") or [],
            task.get("status") or "undone",
            len(self.running_tasks),
            len(self.completed_tasks),
            len(self.pending_tasks),
        )
        slot_id = None
        retry_count = 0
        while self.is_running and slot_id is None and retry_count < 50:
            async with self._worker_lock:
                slot_id = worker_manager["assign_task"](task["task_id"])
            if slot_id is None:
                await asyncio.sleep(min(0.1 + retry_count * 0.02, 0.5))
                retry_count += 1
                if retry_count % 5 == 0:
                    logger.info("Task waiting for worker task_id={} retries={} running_ids={}", task["task_id"], retry_count, sorted(self.running_tasks))
                    self._broadcast_worker_states()
            else:
                break

        if slot_id is None:
            logger.warning("Failed to acquire slot for task {} after {} retries", task["task_id"], retry_count)
            self.completed_tasks.add(task["task_id"])
            self.running_tasks.discard(task["task_id"])
            self.pending_tasks.discard(task["task_id"])
            self._update_task_status(task["task_id"], "done")
            dependents = self.reverse_dependency_index.get(task["task_id"], [])
            self._schedule_ready_tasks([self.task_map[id] for id in dependents if self.task_map.get(id)])
            return

        self.running_tasks.add(task["task_id"])
        logger.info("Task acquired worker task_id={} slot_id={}", task["task_id"], slot_id)
        self._update_task_status(task["task_id"], "doing")
        self._broadcast_worker_states()

        # Emit task-started event with task details
        self._emit("task-started", {
            "taskId": task["task_id"],
            "title": task.get("description", task["task_id"]),
            "description": task.get("description", ""),
            "dependencies": task.get("dependencies") or [],
            "inputKeys": list((task.get("input") or {}).keys()),
            "outputKeys": list((task.get("output") or {}).keys()),
        })
        await self._append_step_event(task["task_id"], "task-started", {
            "description": task.get("description", ""),
            "dependencies": task.get("dependencies") or [],
        })

        try:
            input_spec = task.get("input") or {}
            output_spec = task.get("output") or {}
            if not output_spec:
                raise ValueError(f"Task {task['task_id']} has no output spec")
            execution_error_message = ""
            try:
                resolved_inputs = await resolve_artifacts(task, self.task_map, self.idea_id or "", self.plan_id or "")
                logger.info(
                    "Task resolved inputs task_id={} input_keys={} output_keys={}",
                    task["task_id"],
                    sorted(list((resolved_inputs or {}).keys())) if isinstance(resolved_inputs, dict) else type(resolved_inputs).__name__,
                    sorted(list((output_spec or {}).keys())),
                )

                async def _on_thinking(chunk: str, task_id: Optional[str] = None, operation: Optional[str] = None, schedule_info: Optional[dict] = None) -> None:
                    payload: dict = {"chunk": chunk, "source": "task", "taskId": task_id, "operation": operation or "Execute"}
                    if schedule_info is not None:
                        payload["scheduleInfo"] = schedule_info
                    await self._emit_await("task-thinking", payload)
                    if task_id and chunk:
                        await self._append_step_event(task_id, "task-thinking", {
                            "operation": operation or "Execute",
                            "chunk": chunk,
                            "scheduleInfo": schedule_info or {},
                        })

                api_cfg = self.api_config or {}
                task_container_name = ""
                execution_context = self._build_task_execution_context(task, resolved_inputs)
                if api_cfg.get("taskAgentMode"):
                    if not (self.idea_id and self.plan_id):
                        raise ValueError("Docker task execution requires idea_id and plan_id")
                    runtime = await ensure_execution_container(
                        execution_run_id=self.execution_run_id,
                        idea_id=self.idea_id,
                        plan_id=self.plan_id,
                        task_id=task["task_id"],
                        skills_dir=SKILLS_ROOT,
                        image=api_cfg.get("taskDockerImage"),
                    )
                    task_container_name = runtime.get("containerName") or ""
                    if task_container_name:
                        self.task_docker_containers[task["task_id"]] = task_container_name
                    self.docker_container_name = task_container_name
                    self.docker_runtime_status = {
                        **runtime,
                        "enabled": True,
                        "executionRunId": self.execution_run_id,
                        "taskId": task["task_id"],
                    }
                    self._emit_runtime_status()
                    result = await run_task_agent(
                        task_id=task["task_id"],
                        description=task.get("description") or "",
                        input_spec=input_spec,
                        output_spec=output_spec,
                        resolved_inputs=resolved_inputs,
                        api_config=api_cfg,
                        abort_event=self.abort_event,
                        on_thinking=_on_thinking,
                        idea_id=self.idea_id or "",
                        plan_id=self.plan_id or "",
                        execution_run_id=self.execution_run_id,
                        docker_container_name=task_container_name,
                        validation_spec=task.get("validation"),
                        idea_context=self._idea_text,
                        execution_context=execution_context,
                    )
                else:
                    result = await execute_task(
                        task_id=task["task_id"],
                        description=task.get("description") or "",
                        input_spec=input_spec,
                        output_spec=output_spec,
                        resolved_inputs=resolved_inputs,
                        api_config=api_cfg,
                        abort_event=self.abort_event,
                        on_thinking=_on_thinking,
                        idea_id=self.idea_id or "",
                        plan_id=self.plan_id or "",
                        idea_context=self._idea_text,
                    )
                to_save = result if isinstance(result, dict) else {"content": result}
                await save_task_artifact(self.idea_id or "", self.plan_id or "", task["task_id"], to_save)
                self._emit("task-output", {"taskId": task["task_id"], "output": result})
                await self._append_step_event(task["task_id"], "task-output", {"output": to_save})
                execution_passed = True
            except Exception as exec_err:
                logger.exception("LLM execution failed for task {}", task["task_id"])
                execution_error_message = str(exec_err)
                await self._append_step_event(task["task_id"], "task-execution-error", {"error": execution_error_message})
                execution_passed = False

            if not execution_passed:
                self._update_task_status(task["task_id"], "execution-failed")
                failure_count = self.task_failure_count.get(task["task_id"], 0)
                self.task_failure_count[task["task_id"]] = failure_count + 1
                attempt = failure_count + 1
                will_retry = failure_count < self.MAX_FAILURES - 1
                logger.warning(
                    "Task execution failed task_id={} attempt={}/{}",
                    task["task_id"],
                    attempt,
                    self.MAX_FAILURES,
                )
                self._emit("task-error", {
                    "taskId": task["task_id"],
                    "phase": "execution",
                    "attempt": attempt,
                    "maxAttempts": self.MAX_FAILURES,
                    "willRetry": will_retry,
                    "error": execution_error_message or "Task execution failed",
                })
                await self._record_task_attempt_failure(
                    task_id=task["task_id"],
                    phase="execution",
                    attempt=attempt,
                    error=execution_error_message or "Task execution failed",
                    will_retry=will_retry,
                )
                async with self._worker_lock:
                    worker_manager["release_worker_by_task_id"](task["task_id"])
                self._broadcast_worker_states()
                await asyncio.sleep(1.0)
                if will_retry:
                    next_attempt = failure_count + 2
                    logger.info("Task retry scheduled task_id={} next_attempt={}", task["task_id"], next_attempt)
                    retry_payload = {
                        "taskId": task["task_id"],
                        "phase": "execution",
                        "reason": execution_error_message or "Task execution failed",
                        "attempt": attempt,
                        "nextAttempt": next_attempt,
                        "maxAttempts": self.MAX_FAILURES,
                    }
                    self._emit("task-retry", retry_payload)
                    await self._append_step_event(task["task_id"], "task-retry", retry_payload)
                    self.running_tasks.discard(task["task_id"])
                    self.completed_tasks.discard(task["task_id"])
                    await self._execute_task(task)
                    return
                else:
                    logger.warning("Task rollback after repeated execution failure task_id={}", task["task_id"])
                    self.running_tasks.discard(task["task_id"])
                    self.completed_tasks.discard(task["task_id"])
                    await self._rollback_task(task)
                    return

            # Slot stays held; validation is fixed behavior after execution
            worker_manager["set_worker_status"](task["task_id"], "validating")
            self._broadcast_worker_states()
            self._update_task_status(task["task_id"], "validating")

            # Validation: mock uses random; LLM mode uses LLM validation; Agent mode validates via skill before Finish
            task_id = task["task_id"]
            output_spec = task.get("output") or {}
            use_mock = (self.api_config or {}).get("taskUseMock", True)
            if use_mock:
                validation_passed = random.random() < self.VALIDATION_PASS_PROBABILITY
                report = (
                    f"# Validating Task {task_id}\n\n"
                    "Checking output against criteria...\n\n"
                    "- Criterion 1: Output format ✓\n"
                    "- Criterion 2: Content completeness ✓\n"
                    "- Criterion 3: Alignment with spec ✓\n\n"
                    f"**Result: {'PASS' if validation_passed else 'FAIL'}**\n\n"
                    "(Mock validation mode)"
                )
            else:
                validation_spec = task.get("validation")
                validation_passed, report = await validate_task_output_with_llm(
                    result,
                    output_spec,
                    task_id,
                    validation_spec=validation_spec,
                    api_config=self.api_config,
                    abort_event=self.abort_event,
                    on_thinking=_on_thinking,
                )
            if use_mock:
                for chunk in chunk_string(report, 20):
                    await self._emit_await("task-thinking", {"chunk": chunk, "source": "task", "taskId": task_id, "operation": "Validate"})
                    await asyncio.sleep(_MOCK_VALIDATOR_CHUNK_DELAY)

            if self.idea_id and self.plan_id:
                await save_validation_report(
                    self.idea_id,
                    self.plan_id,
                    task_id,
                    {"passed": validation_passed, "report": report},
                )
            await self._append_step_event(task["task_id"], "task-validation", {
                "passed": validation_passed,
                "report": report,
            })

            await asyncio.sleep(0.1)
            logger.info(
                "Task validation result task_id={} passed={} report_chars={}",
                task_id,
                validation_passed,
                len(report or ""),
            )

            if validation_passed:
                await self._reflect_on_task(task, result, _on_thinking)
                async with self._worker_lock:
                    worker_manager["release_worker_by_task_id"](task["task_id"])
                self._broadcast_worker_states()
                
                # Emit task-completed event with validation result
                self._emit("task-completed", {
                    "taskId": task["task_id"],
                    "validated": True,
                    "validationReport": report[:500] if report else "",  # Truncate long reports
                    "status": "done",
                })
                await self._append_step_event(task["task_id"], "task-completed", {
                    "validated": True,
                    "status": "done",
                })
            else:
                self._update_task_status(task["task_id"], "validation-failed")
                failure_count = self.task_failure_count.get(task["task_id"], 0)
                self.task_failure_count[task["task_id"]] = failure_count + 1
                attempt = failure_count + 1
                will_retry = failure_count < self.MAX_FAILURES - 1
                validation_reason = "Validation failed"
                if report:
                    validation_reason = report[:500]
                logger.warning(
                    "Task validation failed task_id={} attempt={}/{}",
                    task_id,
                    attempt,
                    self.MAX_FAILURES,
                )
                self._emit("task-error", {
                    "taskId": task_id,
                    "phase": "validation",
                    "attempt": attempt,
                    "maxAttempts": self.MAX_FAILURES,
                    "willRetry": will_retry,
                    "error": validation_reason,
                })
                await self._record_task_attempt_failure(
                    task_id=task_id,
                    phase="validation",
                    attempt=attempt,
                    error=validation_reason,
                    will_retry=will_retry,
                )
                await asyncio.sleep(1.0)
                async with self._worker_lock:
                    worker_manager["release_worker_by_task_id"](task["task_id"])
                self._broadcast_worker_states()
                if will_retry:
                    next_attempt = failure_count + 2
                    logger.info("Task retry after validation failure task_id={} next_attempt={}", task_id, next_attempt)
                    retry_payload = {
                        "taskId": task_id,
                        "phase": "validation",
                        "reason": validation_reason,
                        "attempt": attempt,
                        "nextAttempt": next_attempt,
                        "maxAttempts": self.MAX_FAILURES,
                    }
                    self._emit("task-retry", retry_payload)
                    await self._append_step_event(task["task_id"], "task-retry", retry_payload)
                    self.running_tasks.discard(task["task_id"])
                    self.completed_tasks.discard(task["task_id"])
                    await self._execute_task(task)
                    return
                else:
                    logger.warning("Task rollback after repeated validation failure task_id={}", task_id)
                    self.running_tasks.discard(task["task_id"])
                    self.completed_tasks.discard(task["task_id"])
                    await self._rollback_task(task)
                    return

        except Exception as e:
            async with self._worker_lock:
                worker_manager["release_worker_by_task_id"](task["task_id"])
            self._broadcast_worker_states()
            await self._append_step_event(task["task_id"], "task-error", {"error": str(e)})
            raise
        finally:
            task_container_name = self.task_docker_containers.pop(task["task_id"], "")
            if task_container_name:
                try:
                    await stop_execution_container(task_container_name)
                except Exception:
                    logger.exception("Failed to stop Docker task container task_id={} container={}", task["task_id"], task_container_name)
            if self.docker_container_name == task_container_name:
                self.docker_container_name = ""

        self.running_tasks.discard(task["task_id"])
        self.completed_tasks.add(task["task_id"])
        self.pending_tasks.discard(task["task_id"])
        self._update_task_status(task["task_id"], "done")
        self.task_failure_count.pop(task["task_id"], None)
        self.task_attempt_history.pop(task["task_id"], None)
        if self.research_id:
            await delete_task_attempt_memories(self.research_id, task["task_id"])
        logger.info("Task complete task_id={} completed={} remaining_pending={}", task["task_id"], len(self.completed_tasks), len(self.pending_tasks))

        dependents = self.reverse_dependency_index.get(task["task_id"], [])
        candidates = set(dependents)
        for t in self.chain_cache:
            if not (t.get("dependencies") or []):
                if t["task_id"] in self.pending_tasks and t["task_id"] not in self.running_tasks:
                    candidates.add(t["task_id"])
        for task_id in self.pending_tasks:
            if task_id not in self.running_tasks and task_id not in self.completed_tasks:
                pt = self.task_map.get(task_id)
                if pt and self._are_dependencies_satisfied(pt):
                    candidates.add(task_id)

        if candidates:
            logger.info("Task schedule next ready candidates={}", sorted(candidates))

        self._schedule_ready_tasks([self.task_map[id] for id in candidates if self.task_map.get(id)])

    async def _reflect_on_task(self, task: Dict, result: Any, on_thinking) -> None:
        """单个 task 完成后的自迭代：评估质量、可选生成 skill。不做重执行（已有 retry 机制）。"""
        api_cfg = self.api_config or {}
        if not api_cfg.get("reflectionEnabled", False):
            return
        if api_cfg.get("taskUseMock", False):
            return
        try:
            evaluation = await self_evaluate(
                "task", result,
                context={
                    "task_id": task["task_id"],
                    "description": task.get("description", ""),
                    "output_spec": task.get("output") or {},
                },
                on_thinking=on_thinking,
                abort_event=self.abort_event,
                api_config=api_cfg,
            )
            suggestion = evaluation.get("skill_suggestion", {})
            if suggestion.get("should_create") and suggestion.get("name"):
                skill_content = await generate_skill_from_reflection(
                    "task", evaluation,
                    context={"task_id": task["task_id"], "description": task.get("description", "")},
                    api_config=api_cfg, abort_event=self.abort_event,
                )
                if skill_content:
                    save_learned_skill("task", suggestion["name"], skill_content)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Task reflection failed for %s: %s", task["task_id"], e)

    def _schedule_ready_tasks(self, tasks_to_check: List[Dict]) -> None:
        if not tasks_to_check or not self.is_running:
            return
        ready = [
            t for t in tasks_to_check
            if t and t["task_id"] not in self.completed_tasks
            and t["task_id"] not in self.running_tasks
            and t["task_id"] in self.pending_tasks
            and self._are_dependencies_satisfied(t)
        ]
        for task in ready:
            if task["task_id"] not in self.task_tasks:
                async def run_with_error_handling(t=task):
                    try:
                        await self._execute_task(t)
                    except Exception as e:
                        await self._handle_task_error(t, e)

                self.task_tasks[task["task_id"]] = asyncio.create_task(run_with_error_handling())

    async def _handle_task_error(self, task: Dict, error: Exception) -> None:
        logger.exception("Error executing task %s", task["task_id"])
        self._emit("task-error", {
            "taskId": task["task_id"],
            "phase": "execution",
            "willRetry": False,
            "error": str(error),
        })
        async with self._worker_lock:
            worker_manager["release_worker_by_task_id"](task["task_id"])
        self._broadcast_worker_states()
        self.completed_tasks.add(task["task_id"])
        self.running_tasks.discard(task["task_id"])
        self.pending_tasks.discard(task["task_id"])
        self._update_task_status(task["task_id"], "execution-failed")
        dependents = self.reverse_dependency_index.get(task["task_id"], [])
        self._schedule_ready_tasks([self.task_map[id] for id in dependents if self.task_map.get(id)])

    def _are_dependencies_satisfied(self, task: Dict) -> bool:
        deps = task.get("dependencies") or []
        if not deps:
            return True
        return all(d in self.completed_tasks for d in deps)

    def _update_task_status(self, task_id: str, status: str) -> None:
        t = self.task_map.get(task_id)
        if t:
            t["status"] = status
        try:
            asyncio.create_task(self._append_step_event(task_id, "task-status", {"status": status}))
        except RuntimeError:
            pass
        self._persist_execution()
        self._broadcast_task_states()

    async def _append_step_event(self, task_id: str, event: str, payload: Dict[str, Any]) -> None:
        if not self.execution_run_id or not task_id:
            return
        try:
            step_dir = get_execution_task_step_dir(self.execution_run_id, task_id).resolve()
            step_dir.mkdir(parents=True, exist_ok=True)
            path = step_dir / "events.jsonl"
            record = {
                "ts": int(time.time() * 1000),
                "runId": self.execution_run_id,
                "taskId": task_id,
                "event": event,
                "payload": payload or {},
            }
            line = json.dumps(record, ensure_ascii=False) + "\n"
            await asyncio.to_thread(self._append_line, path, line)
        except Exception as e:
            logger.debug("Failed to append step event task_id={} event={} error={}", task_id, event, e)

    @staticmethod
    def _append_line(path: Path, line: str) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(line)

    async def _stop_all_task_containers(self) -> None:
        containers = list(self.task_docker_containers.values())
        self.task_docker_containers.clear()
        for container_name in containers:
            try:
                await stop_execution_container(container_name)
            except Exception:
                logger.exception("Failed to stop Docker execution container {}", container_name)
        self.docker_container_name = ""

    def _broadcast_task_states(self) -> None:
        task_states = [{"task_id": t["task_id"], "status": t["status"]} for t in self.chain_cache]
        self._emit("task-states-update", {"tasks": task_states})

    def _broadcast_worker_states(self) -> None:
        """Broadcast execution concurrency stats. (Frontend uses syncExecutionStateOnConnect for stats.)"""

    async def _rollback_task(self, task: Dict) -> None:
        """Rollback failed task and all downstream dependents.
        Upstream dependencies remain completed and are reused for retry."""
        tasks_to_rollback: Set[str] = set()
        tasks_to_rollback.add(task["task_id"])

        visited: Set[str] = set()

        def find_downstream(tid: str) -> None:
            if tid in visited:
                return
            visited.add(tid)
            for dep_id in self.reverse_dependency_index.get(tid, []):
                if dep_id not in tasks_to_rollback:
                    tasks_to_rollback.add(dep_id)
                    find_downstream(dep_id)

        # Downstream of the rolled-back task: all dependents become unreliable
        find_downstream(task["task_id"])

        async with self._worker_lock:
            for task_id in tasks_to_rollback:
                t = self.task_map.get(task_id)
                if t:
                    self.completed_tasks.discard(task_id)
                    self.pending_tasks.add(task_id)
                    self.running_tasks.discard(task_id)
                    self._update_task_status(task_id, "undone")
                    self.task_failure_count.pop(task_id, None)
                    self.task_tasks.pop(task_id, None)
                    worker_manager["release_worker_by_task_id"](task_id)
                # P0: Clean artifact so downstream re-runs read fresh data
                if self.idea_id and self.plan_id:
                    await delete_task_artifact(self.idea_id, self.plan_id, task_id)

        self._broadcast_worker_states()

        ready = [
            self.task_map[tid]
            for tid in tasks_to_rollback
            if self.task_map.get(tid)
            and self._are_dependencies_satisfied(self.task_map[tid])
            and tid in self.pending_tasks
        ]
        if ready:
            self._schedule_ready_tasks(ready)

    def set_layout(
        self,
        layout: Dict,
        idea_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        execution: Optional[Dict] = None,
    ) -> None:
        if self.is_running:
            raise ValueError("Cannot set layout while execution is running")
        self.execution_layout = layout
        self.idea_id = idea_id
        self.plan_id = plan_id
        self.chain_cache = []
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
                self.chain_cache.append({
                    "task_id": tid,
                    "title": full.get("title") or t.get("title"),
                    "dependencies": t.get("dependencies") or [],
                    "status": status,
                    "description": full.get("description") or t.get("description"),
                    "input": full.get("input") or t.get("input"),
                    "output": full.get("output") or t.get("output"),
                    "validation": full.get("validation") or t.get("validation"),
                })

    async def retry_task(self, task_id: str) -> bool:
        """
        Retry a single failed task. If execution is running, reset and re-schedule in-place.
        If not running, start execution with resume_from_task_id.
        Returns True if retry was initiated.
        """
        if task_id not in self.task_map:
            return False
        task = self.task_map[task_id]
        status = task.get("status")
        if status not in ("execution-failed", "validation-failed"):
            return False

        if self.is_running:
            self.completed_tasks.discard(task_id)
            self.running_tasks.discard(task_id)
            self.pending_tasks.add(task_id)
            self.task_failure_count.pop(task_id, None)
            self.task_tasks.pop(task_id, None)
            task["status"] = "undone"
            if self.idea_id and self.plan_id:
                await delete_task_artifact(self.idea_id, self.plan_id, task_id)
            self._persist_execution()
            self._broadcast_task_states()
            self._schedule_ready_tasks([task])
            return True
        return False

    async def stop_async(self) -> None:
        """停止 Task Agent Execution 阶段：发送中止信号，取消任务，释放 worker，立即推送 task-error。"""
        self.is_running = False
        if self.abort_event:
            self.abort_event.set()
        self._emit("task-error", {"error": "Task execution stopped by user"})
        task_ids = list(self.task_tasks.keys())
        for task_id in task_ids:
            asyncio_task = self.task_tasks.get(task_id)
            if asyncio_task and not asyncio_task.done():
                asyncio_task.cancel()
        async with self._worker_lock:
            for task_id in task_ids:
                worker_manager["release_worker_by_task_id"](task_id)
        self.task_tasks.clear()
        self.running_tasks.clear()
        await self._stop_all_task_containers()
        self.docker_runtime_status = await get_local_docker_status(enabled=bool((self.api_config or {}).get("taskAgentMode")))
        self._emit_runtime_status()
        self._broadcast_worker_states()
