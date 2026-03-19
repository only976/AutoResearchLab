"""
Task Agent 实现 - Execution 阶段编排器，管理 worker pool。
Task Agent 含两阶段：Execution（执行原子任务）→ Validation（验证产出）。每个 task 依次经历两阶段。
单轮 LLM 在 task_agent/llm/。
"""

import asyncio
import os
import time
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from shared.constants import (
    MAX_EXECUTION_CONCURRENCY,
    MOCK_EXECUTION_PASS_PROBABILITY,
    MOCK_VALIDATION_PASS_PROBABILITY,
)
from shared.idea_utils import get_idea_text
from db import save_execution as _db_save_execution
from .runner_deps import RunnerDeps, build_default_deps
from . import runner_orchestration as exec_fns
from . import runner_memory as memory_fns
from . import runner_retry as retry_fns
from . import runner_scheduling as state_fns
from . import runner_phases as task_exec_fns


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
    def __init__(self, sio: Any, session_id: Optional[str] = None, deps: Optional[RunnerDeps] = None):
        self.sio = sio
        self.session_id = session_id
        self._deps = deps or build_default_deps()
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
        self.task_phase_failure_count: Dict[str, int] = {}
        self.task_last_retry_attempt: Dict[str, int] = {}
        self.EXECUTION_PASS_PROBABILITY = MOCK_EXECUTION_PASS_PROBABILITY
        self.VALIDATION_PASS_PROBABILITY = MOCK_VALIDATION_PASS_PROBABILITY
        self.MAX_RETRY_ATTEMPTS = 5
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
        self.task_run_attempt: Dict[str, int] = {}
        self.task_attempt_history: Dict[str, List[Dict[str, Any]]] = {}
        self.task_forced_attempt: Dict[str, int] = {}
        self.task_next_attempt_hint: Dict[str, int] = {}
        self.task_execute_started_attempts: Dict[str, Set[int]] = {}
        self.research_id: str = ""

    # -- Emit / persist helpers (inlined from RunnerEmitMixin) --

    def _persist_execution(self) -> None:
        if self.idea_id and self.plan_id and self.chain_cache:
            try:
                asyncio.create_task(self._persist_execution_async())
            except RuntimeError:
                pass

    async def _persist_execution_async(self) -> None:
        async with self._persist_lock:
            if self.idea_id and self.plan_id and self.chain_cache:
                try:
                    await _db_save_execution({"tasks": list(self.chain_cache)}, self.idea_id, self.plan_id)
                except Exception as e:
                    logger.warning("Failed to persist execution: %s", e)

    def _emit(self, event: str, data: dict) -> None:
        if hasattr(self.sio, "emit"):
            try:
                asyncio.create_task(self.sio.emit(event, data, to=self.session_id))
            except RuntimeError:
                pass

    async def _emit_await(self, event: str, data: dict) -> None:
        if hasattr(self.sio, "emit"):
            try:
                await self.sio.emit(event, data, to=self.session_id)
            except Exception as e:
                logger.warning("%s emit failed: %s", event, e)

    # -- Retry/attempt delegates (from runner_retry) --

    def _failure_key(self, task_id: str, bucket: str) -> str:
        return retry_fns.failure_key(task_id, bucket)

    def _get_failure_count(self, task_id: str, bucket: str) -> int:
        return retry_fns.get_failure_count(self.task_phase_failure_count, task_id, bucket)

    def _clear_task_failure_counts(self, task_id: str) -> None:
        retry_fns.clear_task_failure_counts(self.task_phase_failure_count, self.task_failure_count, task_id)

    @staticmethod
    def _extract_direct_fail_reason(report_text: str) -> str:
        return retry_fns.extract_direct_fail_reason(report_text)

    def _next_retry_attempt(self, task_id: str) -> int:
        return retry_fns.next_retry_attempt(self.task_attempt_history, self.task_phase_failure_count, task_id)

    def _get_current_attempt(self, task_id: str) -> int:
        return retry_fns.get_current_attempt(self.task_attempt_history, self.task_phase_failure_count, task_id)

    def _resolve_run_attempt(self, task_id: str) -> int:
        return retry_fns.resolve_run_attempt(
            self.task_run_attempt, self.task_forced_attempt, self.task_next_attempt_hint,
            self.task_attempt_history, self.task_phase_failure_count, task_id,
        )

    def _reserve_execute_attempt(self, task_id: str, requested_attempt: int) -> int:
        return retry_fns.reserve_execute_attempt(self.task_execute_started_attempts, task_id, requested_attempt)

    def _get_original_validation_criteria(self, task: Dict) -> List[str]:
        return retry_fns.get_original_validation_criteria(task)

    @staticmethod
    def _run_step_a_structural_format_gate(result: Any, output_spec: Dict[str, Any]) -> tuple[bool, str]:
        return retry_fns.run_step_a_structural_format_gate(result, output_spec)

    # -- Memory delegates (from runner_memory) --

    async def _record_task_attempt_failure(
        self, *, task_id: str, phase: str, attempt: int, error: str,
        will_retry: bool, decision: Optional[Dict[str, Any]] = None,
    ) -> None:
        await memory_fns.record_task_attempt_failure(
            self.task_attempt_history, self.research_id, self._deps.save_task_attempt_memory,
            task_id=task_id, phase=phase, attempt=attempt, error=error,
            will_retry=will_retry, decision=decision,
        )

    async def _load_task_attempt_memories(self) -> None:
        await memory_fns.load_task_attempt_memories(
            self.task_attempt_history, self.research_id, self._deps.list_task_attempt_memories,
        )

    async def _clear_attempt_history_for_tasks(self, task_ids: Set[str]) -> None:
        await memory_fns.clear_attempt_history_for_tasks(
            self.task_attempt_history, self.research_id, self._deps.delete_task_attempt_memories, task_ids,
        )

    def _build_task_execution_context(self, task: Dict[str, Any], resolved_inputs: Dict[str, Any]) -> Dict[str, Any]:
        return memory_fns.build_task_execution_context(
            task=task, resolved_inputs=resolved_inputs,
            completed_tasks=self.completed_tasks, task_attempt_history=self.task_attempt_history,
            chain_cache=self.chain_cache, idea_text=self._idea_text,
            execution_run_id=self.execution_run_id,
        )

    # -- State/scheduling delegates (from runner_scheduling) --

    def _schedule_ready_tasks(self, tasks_to_check: List[Dict]) -> None:
        state_fns.schedule_ready_tasks(self, tasks_to_check)

    async def _handle_task_error(self, task: Dict, error: Exception) -> None:
        await state_fns.handle_task_error(self, task, error)

    async def _trigger_fail_fast(self, *, failed_task_id: str, phase: str, reason: str) -> None:
        await state_fns.trigger_fail_fast(self, failed_task_id=failed_task_id, phase=phase, reason=reason)

    def _are_dependencies_satisfied(self, task: Dict) -> bool:
        return state_fns.are_dependencies_satisfied(self.completed_tasks, task)

    def _update_task_status(self, task_id: str, status: str) -> None:
        state_fns.update_task_status(self, task_id, status)

    async def _append_step_event(self, task_id: str, event: str, payload: Dict[str, Any]) -> None:
        await state_fns.append_step_event(self.execution_run_id, task_id, event, payload)

    async def _stop_all_task_containers(self) -> None:
        await state_fns.stop_all_task_containers(self)

    def _broadcast_task_states(self) -> None:
        state_fns.broadcast_task_states(self)

    def _broadcast_worker_states(self) -> None:
        state_fns.broadcast_worker_states(self)

    async def _rollback_task(self, task: Dict) -> None:
        await state_fns.rollback_task(self, task)

    def set_layout(self, layout: Dict, idea_id: Optional[str] = None, plan_id: Optional[str] = None, execution: Optional[Dict] = None) -> None:
        state_fns.set_layout(self, layout, idea_id, plan_id, execution)

    async def retry_task(self, task_id: str) -> bool:
        return await state_fns.retry_task(self, task_id)

    async def stop_async(self) -> None:
        await state_fns.stop_async(self)

    # -- Execution orchestration delegates (from runner_orchestration) --

    def _find_dependency_gap(self) -> Optional[Dict[str, str]]:
        return exec_fns.find_dependency_gap(self)

    async def _run_step_b_contract_review(self, *, task, result, reason, output_format, on_thinking=None):
        return await exec_fns.run_step_b_contract_review(
            self, task=task, result=result, reason=reason,
            output_format=output_format, on_thinking=on_thinking,
        )

    async def _retry_or_fail(self, *, task, phase, error, decision=None):
        await exec_fns.retry_or_fail(self, task=task, phase=phase, error=error, decision=decision)

    def _get_ready_tasks(self) -> List[Dict]:
        return exec_fns.get_ready_tasks(self)

    async def _execute_tasks(self) -> None:
        await exec_fns.execute_tasks(self)

    # -- Task execution delegates (from runner_phases) --

    async def _persist_attempt_prompt_snapshot(self, *, task_id, attempt, prompt_payload):
        await task_exec_fns.persist_attempt_prompt_snapshot(
            self, task_id=task_id, attempt=attempt, prompt_payload=prompt_payload,
        )

    def _make_on_thinking_callback(self, task: Dict, run_attempt: int):
        return task_exec_fns.make_on_thinking_callback(self, task, run_attempt)

    async def _phase_execute(self, task, run_attempt, on_thinking):
        return await task_exec_fns.phase_execute(self, task, run_attempt, on_thinking)

    async def _phase_validate(self, task, result, resolved_inputs, run_attempt, on_thinking):
        return await task_exec_fns.phase_validate(self, task, result, resolved_inputs, run_attempt, on_thinking)

    async def _phase_finalize_success(self, task, run_attempt, report, validation_summary):
        await task_exec_fns.phase_finalize_success(self, task, run_attempt, report, validation_summary)

    async def _execute_task(self, task: Dict) -> None:
        await task_exec_fns.execute_task(self, task)

    async def _reflect_on_task(self, task, result, on_thinking):
        await task_exec_fns.reflect_on_task(self, task, result, on_thinking)

    # -- Task lifecycle --

    def _spawn_task_execution(self, task: Dict) -> None:
        task_id = task["task_id"]
        existing = self.task_tasks.get(task_id)
        if existing and not existing.done():
            # When retry is triggered from inside the task's own coroutine,
            # allow replacing this in-flight handle so the next attempt can start.
            current = asyncio.current_task()
            if existing is not current:
                return
            self.task_tasks.pop(task_id, None)

        async def run_with_error_handling(t=task):
            try:
                await self._execute_task(t)
            except Exception as e:
                await self._handle_task_error(t, e)

        created = asyncio.create_task(run_with_error_handling())
        self.task_tasks[task_id] = created

        def _cleanup(done_task: asyncio.Task, tid: str = task_id) -> None:
            current = self.task_tasks.get(tid)
            if current is done_task:
                self.task_tasks.pop(tid, None)

        created.add_done_callback(_cleanup)

    def _emit_runtime_status(self) -> None:
        payload = dict(self.docker_runtime_status or {})
        payload["executionRunId"] = self.execution_run_id
        payload["ideaId"] = self.idea_id or ""
        payload["planId"] = self.plan_id or ""
        self._emit("execution-runtime-status", payload)

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
        # Attempt history is scoped to one execute run. Start of a new run clears persisted memories.
        if self.research_id:
            try:
                await self._deps.delete_task_attempt_memories(self.research_id)
            except Exception:
                logger.exception("Failed to clear task attempt memories for new run research_id={}", self.research_id)
        self.task_attempt_history.clear()
        if self.idea_id:
            try:
                idea_data = await self._deps.get_idea(self.idea_id)
                if idea_data:
                    refined = idea_data.get("refined_idea")
                    self._idea_text = get_idea_text(refined) or (idea_data.get("idea") or "").strip()
            except Exception:
                pass
        try:
            max_conc = MAX_EXECUTION_CONCURRENCY
            self._deps.initialize_workers(max_conc)
            self._broadcast_worker_states()

            api_cfg = self.api_config or {}
            docker_enabled = bool(api_cfg.get("taskAgentMode"))
            if docker_enabled:
                self.docker_runtime_status = await self._deps.prepare_execution_runtime(
                    enabled=True,
                    image=api_cfg.get("taskDockerImage"),
                )
            else:
                self.docker_runtime_status = await self._deps.get_local_docker_status(enabled=False)
            self._emit_runtime_status()

            execution_layout = self.execution_layout
            self.running_tasks.clear()
            self.completed_tasks.clear()
            self.pending_tasks.clear()
            self.task_tasks.clear()
            self.task_map.clear()
            self.reverse_dependency_index.clear()
            self.task_failure_count.clear()
            self.task_phase_failure_count.clear()
            self.task_last_retry_attempt.clear()
            self.task_run_attempt.clear()
            self.task_forced_attempt.clear()
            self.task_next_attempt_hint.clear()
            self.task_execute_started_attempts.clear()

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
                            await self._deps.delete_task_artifact(self.idea_id, self.plan_id, task["task_id"])
                        self.pending_tasks.add(task["task_id"])
                        self.completed_tasks.discard(task["task_id"])
                        self._clear_task_failure_counts(task["task_id"])
                    elif task.get("status") == "done":
                        self.completed_tasks.add(task["task_id"])
                        self.pending_tasks.discard(task["task_id"])
                await self._clear_attempt_history_for_tasks(set(to_reset))
            else:
                for task in self.chain_cache:
                    task["status"] = "undone"
            if self.idea_id and self.plan_id and self.chain_cache:
                await self._deps.save_execution({"tasks": self.chain_cache}, self.idea_id, self.plan_id)

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
            self.docker_runtime_status = await self._deps.get_local_docker_status(enabled=bool((self.api_config or {}).get("taskAgentMode")))
            self._emit_runtime_status()
            self._deps.initialize_workers()
            self._broadcast_worker_states()


