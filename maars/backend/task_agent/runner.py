"""
Task Agent 实现 - Execution Runner，编排 worker pool。
Each task: Execute → Validate (validation is fixed behavior). Task status persisted to execution.json in real-time.
单轮 LLM 在 task_agent/llm/。
"""

import asyncio
import os
import random
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from db import delete_task_artifact, save_execution, save_task_artifact, save_validation_report
from shared.utils import chunk_string
from .pools import worker_manager
from .artifact_resolver import resolve_artifacts
from .agent import run_task_agent
from .llm.executor import execute_task
from .llm.validation import validate_task_output_with_llm

# Mock validation chunk delay (seconds), same as task execution for consistent streaming UX
_MOCK_VALIDATOR_CHUNK_DELAY = 0.03

# Configurable via env (Mock mode); defaults for tuning
def _float_env(name: str, default: float) -> float:
    v = os.environ.get(name)
    return float(v) if v is not None else default

def _int_env(name: str, default: int) -> int:
    v = os.environ.get(name)
    return int(v) if v is not None else default

_RUNNER_EXECUTION_PASS_PROBABILITY = _float_env("MAARS_EXECUTION_PASS_PROBABILITY", 0.95)
_RUNNER_VALIDATION_PASS_PROBABILITY = _float_env("MAARS_VALIDATION_PASS_PROBABILITY", 0.95)
_RUNNER_MAX_FAILURES = _int_env("MAARS_MAX_FAILURES", 3)


class ExecutionRunner:
    def __init__(self, sio: Any):
        self.sio = sio
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
        self.EXECUTION_PASS_PROBABILITY = _RUNNER_EXECUTION_PASS_PROBABILITY
        self.VALIDATION_PASS_PROBABILITY = _RUNNER_VALIDATION_PASS_PROBABILITY
        self.MAX_FAILURES = _RUNNER_MAX_FAILURES
        self.execution_layout = None
        self.plan_id: Optional[str] = None
        self.api_config: Optional[Dict] = None
        self.abort_event: Optional[asyncio.Event] = None
        self._persist_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()

    def _persist_execution(self) -> None:
        """Persist chain_cache to execution.json. Serialized via _persist_lock to avoid concurrent write races."""
        if self.plan_id and self.chain_cache:
            try:
                asyncio.create_task(self._persist_execution_async())
            except RuntimeError:
                pass

    async def _persist_execution_async(self) -> None:
        """Serialized persist: prevents multiple save_execution from overwriting each other with stale data."""
        async with self._persist_lock:
            if self.plan_id and self.chain_cache:
                try:
                    await save_execution({"tasks": list(self.chain_cache)}, self.plan_id)
                except Exception as e:
                    logger.warning("Failed to persist execution: %s", e)

    def _emit(self, event: str, data: dict) -> None:
        """Emit event to all clients (fire-and-forget)."""
        if hasattr(self.sio, "emit"):
            try:
                asyncio.create_task(self.sio.emit(event, data))
            except RuntimeError:
                pass

    async def _emit_await(self, event: str, data: dict) -> None:
        """Emit event and await; use for order-sensitive events (e.g. thinking chunks)."""
        if hasattr(self.sio, "emit"):
            try:
                await self.sio.emit(event, data)
            except Exception:
                pass

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

    async def start_execution(
        self,
        api_config: Optional[Dict] = None,
        resume_from_task_id: Optional[str] = None,
    ) -> None:
        if api_config is not None:
            self.api_config = api_config
            mode_cfg = api_config.get("modeConfig") or {}
            mock_cfg = mode_cfg.get("mock") or {}
            if mock_cfg:
                v = mock_cfg.get("executionPassProbability")
                if v is not None:
                    self.EXECUTION_PASS_PROBABILITY = float(v)
                v = mock_cfg.get("validationPassProbability")
                if v is not None:
                    self.VALIDATION_PASS_PROBABILITY = float(v)
            # maxFailures: read from mock | llm | llmagent | agent
            use_mock = api_config.get("useMock", True)
            exec_agent = api_config.get("taskAgentMode", False)
            ai_mode = api_config.get("aiMode") or ""
            if use_mock:
                runner_cfg = mock_cfg
            elif exec_agent:
                runner_cfg = mode_cfg.get(ai_mode) or mode_cfg.get("agent") or {}
            else:
                runner_cfg = mode_cfg.get("llm") or {}
            v = runner_cfg.get("maxFailures")
            if v is not None:
                self.MAX_FAILURES = int(v)
        async with self._start_lock:
            if self.is_running:
                raise ValueError("Execution is already running")
            if not self.chain_cache:
                raise ValueError("No execution map cache found. Please generate map first.")
            if not self.execution_layout:
                raise ValueError("No execution layout cache found. Please generate layout first.")
            self.is_running = True
        self.abort_event = asyncio.Event()
        self.abort_event.clear()
        try:
            max_conc = (self.api_config or {}).get("maxExecutionConcurrency", 7)
            worker_manager["initialize_workers"](max_conc)
            self._broadcast_worker_states()

            execution_layout = self.execution_layout
            self.running_tasks.clear()
            self.completed_tasks.clear()
            self.pending_tasks.clear()
            self.task_tasks.clear()
            self.task_map.clear()
            self.reverse_dependency_index.clear()
            self.task_failure_count.clear()

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
                        if self.plan_id:
                            await delete_task_artifact(self.plan_id, task["task_id"])
                        self.pending_tasks.add(task["task_id"])
                        self.completed_tasks.discard(task["task_id"])
                        self.task_failure_count.pop(task["task_id"], None)
                    elif task.get("status") == "done":
                        self.completed_tasks.add(task["task_id"])
                        self.pending_tasks.discard(task["task_id"])
            else:
                for task in self.chain_cache:
                    task["status"] = "undone"
            if self.plan_id and self.chain_cache:
                await save_execution({"tasks": self.chain_cache}, self.plan_id)

            self._emit("execution-start", {})
            self._emit("execution-layout", {"layout": execution_layout})
            self._broadcast_task_states()
            await self._execute_tasks()
        except Exception as e:
            logger.exception("Error in execution")
            self._emit("execution-error", {"error": str(e)})
            raise
        finally:
            self.is_running = False
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
        logger.info("Found %d initial ready tasks out of %d total tasks", len(initial_ready), len(self.chain_cache))

        for task in initial_ready:
            async def run_with_error_handling(t=task):
                try:
                    await self._execute_task(t)
                except Exception as e:
                    await self._handle_task_error(t, e)

            self.task_tasks[task["task_id"]] = asyncio.create_task(run_with_error_handling())

        # Event-driven: wait for completion (task completion triggers _schedule_ready_tasks)
        while self.is_running and (len(self.completed_tasks) < len(self.chain_cache) or len(self.running_tasks) > 0):
            await asyncio.sleep(0.1)

        logger.info("Final state: %d/%d tasks completed", len(self.completed_tasks), len(self.chain_cache))
        if self.is_running:
            self._emit("execution-complete", {"completed": len(self.completed_tasks), "total": len(self.chain_cache)})
        else:
            self._emit("execution-error", {"error": "Execution stopped by user"})

    async def _execute_task(self, task: Dict) -> None:
        if not self.is_running:
            return
        slot_id = None
        retry_count = 0
        while self.is_running and slot_id is None and retry_count < 50:
            async with self._worker_lock:
                slot_id = worker_manager["assign_task"](task["task_id"])
            if slot_id is None:
                await asyncio.sleep(min(0.1 + retry_count * 0.02, 0.5))
                retry_count += 1
                if retry_count % 5 == 0:
                    self._broadcast_worker_states()
            else:
                break

        if slot_id is None:
            logger.warning("Failed to acquire slot for task %s after %d retries", task["task_id"], retry_count)
            self.completed_tasks.add(task["task_id"])
            self.running_tasks.discard(task["task_id"])
            self.pending_tasks.discard(task["task_id"])
            self._update_task_status(task["task_id"], "done")
            dependents = self.reverse_dependency_index.get(task["task_id"], [])
            self._schedule_ready_tasks([self.task_map[id] for id in dependents if self.task_map.get(id)])
            return

        self.running_tasks.add(task["task_id"])
        self._update_task_status(task["task_id"], "doing")
        self._broadcast_worker_states()

        try:
            input_spec = task.get("input") or {}
            output_spec = task.get("output") or {}
            if not output_spec:
                raise ValueError(f"Task {task['task_id']} has no output spec")
            try:
                resolved_inputs = await resolve_artifacts(task, self.task_map, self.plan_id or "")

                async def _on_thinking(chunk: str, task_id: Optional[str] = None, operation: Optional[str] = None, schedule_info: Optional[dict] = None) -> None:
                    payload: dict = {"chunk": chunk, "taskId": task_id, "operation": operation or "Execute"}
                    if schedule_info is not None:
                        payload["scheduleInfo"] = schedule_info
                    await self._emit_await("task-thinking", payload)

                api_cfg = self.api_config or {}
                if api_cfg.get("taskAgentMode"):
                    result = await run_task_agent(
                        task_id=task["task_id"],
                        description=task.get("description") or "",
                        input_spec=input_spec,
                        output_spec=output_spec,
                        resolved_inputs=resolved_inputs,
                        api_config=api_cfg,
                        abort_event=self.abort_event,
                        on_thinking=_on_thinking,
                        plan_id=self.plan_id or "",
                        validation_spec=task.get("validation"),
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
                        plan_id=self.plan_id or "",
                    )
                to_save = result if isinstance(result, dict) else {"content": result}
                await save_task_artifact(self.plan_id or "", task["task_id"], to_save)
                self._emit("task-output", {"taskId": task["task_id"], "output": result})
                execution_passed = True
            except Exception as exec_err:
                logger.warning("LLM execution failed for task %s: %s", task["task_id"], exec_err)
                execution_passed = False

            if not execution_passed:
                self._update_task_status(task["task_id"], "execution-failed")
                failure_count = self.task_failure_count.get(task["task_id"], 0)
                self.task_failure_count[task["task_id"]] = failure_count + 1
                async with self._worker_lock:
                    worker_manager["release_worker_by_task_id"](task["task_id"])
                self._broadcast_worker_states()
                await asyncio.sleep(1.0)
                if failure_count < self.MAX_FAILURES - 1:
                    self.running_tasks.discard(task["task_id"])
                    self.completed_tasks.discard(task["task_id"])
                    await self._execute_task(task)
                    return
                else:
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
            use_mock = (self.api_config or {}).get("useMock", True)
            exec_agent = (self.api_config or {}).get("taskAgentMode", False)
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
            elif exec_agent:
                # Agent mode: Agent validates via task-output-validator skill before Finish
                validation_passed = True
                report = (
                    f"# Validating Task {task_id}\n\n"
                    "Validated by Agent via task-output-validator skill before Finish.\n\n"
                    "**Result: PASS**"
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
                )
            for chunk in chunk_string(report, 20):
                await self._emit_await("task-thinking", {"chunk": chunk, "taskId": task_id, "operation": "Validate"})
                await asyncio.sleep(_MOCK_VALIDATOR_CHUNK_DELAY)

            if self.plan_id:
                await save_validation_report(
                    self.plan_id,
                    task_id,
                    {"passed": validation_passed, "report": report},
                )

            await asyncio.sleep(0.1)

            if validation_passed:
                async with self._worker_lock:
                    worker_manager["release_worker_by_task_id"](task["task_id"])
                self._broadcast_worker_states()
            else:
                self._update_task_status(task["task_id"], "validation-failed")
                failure_count = self.task_failure_count.get(task["task_id"], 0)
                self.task_failure_count[task["task_id"]] = failure_count + 1
                await asyncio.sleep(1.0)
                async with self._worker_lock:
                    worker_manager["release_worker_by_task_id"](task["task_id"])
                self._broadcast_worker_states()
                if failure_count < self.MAX_FAILURES - 1:
                    self.running_tasks.discard(task["task_id"])
                    self.completed_tasks.discard(task["task_id"])
                    await self._execute_task(task)
                    return
                else:
                    self.running_tasks.discard(task["task_id"])
                    self.completed_tasks.discard(task["task_id"])
                    await self._rollback_task(task)
                    return

        except Exception as e:
            async with self._worker_lock:
                worker_manager["release_worker_by_task_id"](task["task_id"])
            self._broadcast_worker_states()
            raise

        self.running_tasks.discard(task["task_id"])
        self.completed_tasks.add(task["task_id"])
        self.pending_tasks.discard(task["task_id"])
        self._update_task_status(task["task_id"], "done")
        self.task_failure_count.pop(task["task_id"], None)

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

        self._schedule_ready_tasks([self.task_map[id] for id in candidates if self.task_map.get(id)])

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
        self._persist_execution()
        self._broadcast_task_states()

    def _broadcast_task_states(self) -> None:
        task_states = [{"task_id": t["task_id"], "status": t["status"]} for t in self.chain_cache]
        self._emit("task-states-update", {"tasks": task_states})

    def _broadcast_worker_states(self) -> None:
        """Broadcast execution concurrency stats."""
        stats = worker_manager["get_worker_stats"]()
        self._emit("execution-stats-update", {"stats": stats})

    async def _rollback_task(self, task: Dict) -> None:
        """Rollback task and all affected: upstream deps + downstream dependents.
        Once a task is undone, its downstream results are unreliable and must be undone too."""
        tasks_to_rollback: Set[str] = set()
        tasks_to_rollback.add(task["task_id"])
        for dep_id in (task.get("dependencies") or []):
            tasks_to_rollback.add(dep_id)

        visited: Set[str] = set()

        def find_downstream(tid: str) -> None:
            if tid in visited:
                return
            visited.add(tid)
            for dep_id in self.reverse_dependency_index.get(tid, []):
                if dep_id not in tasks_to_rollback:
                    tasks_to_rollback.add(dep_id)
                    find_downstream(dep_id)

        for dep_id in (task.get("dependencies") or []):
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
                if self.plan_id:
                    await delete_task_artifact(self.plan_id, task_id)

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
        plan_id: Optional[str] = None,
        execution: Optional[Dict] = None,
    ) -> None:
        if self.is_running:
            raise ValueError("Cannot set layout while execution is running")
        self.execution_layout = layout
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
            if self.plan_id:
                await delete_task_artifact(self.plan_id, task_id)
            self._persist_execution()
            self._broadcast_task_states()
            self._schedule_ready_tasks([task])
            return True
        return False

    async def stop_async(self) -> None:
        """Stop execution: signal abort (stops API calls/token use), cancel tasks, release workers."""
        self.is_running = False
        if self.abort_event:
            self.abort_event.set()
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
        self._broadcast_worker_states()
