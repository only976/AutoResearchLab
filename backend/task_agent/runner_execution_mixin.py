"""Execution-phase orchestration helpers for Task ExecutionRunner."""

import asyncio
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from .runner_task_execution_mixin import RunnerTaskExecutionMixin


def _runner_module():
    from . import runner as runner_mod

    return runner_mod


class RunnerExecutionMixin(RunnerTaskExecutionMixin):
    def _find_dependency_gap(self) -> Optional[Dict[str, str]]:
        """Find a task waiting on a dependency that is in neither todo nor completed sets."""
        todo_ids = set(self.pending_tasks) | set(self.running_tasks)
        completed_ids = set(self.completed_tasks)
        for task in self.chain_cache:
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

    async def _run_step_b_contract_review(
        self,
        *,
        task: Dict[str, Any],
        result: Any,
        reason: str,
        output_format: str,
        on_thinking: Optional[Any] = None,
    ) -> Dict[str, Any]:
        runner_mod = _runner_module()
        task_id = str(task.get("task_id") or "")
        validation = task.setdefault("validation", {})
        if not isinstance(validation, dict):
            validation = {}
            task["validation"] = validation
        original = self._get_original_validation_criteria(task)
        active = list(validation.get("criteria") or [])

        packet = {
            "task": {
                "taskId": task_id,
                "description": task.get("description") or "",
                "outputFormat": output_format or "",
            },
            "globalGoal": self._idea_text or "",
            "attemptHistory": list(self.task_attempt_history.get(task_id) or []),
            "initialValidationCriteria": original,
            "activeValidationCriteria": active,
            "resultPreview": (result if isinstance(result, dict) else {"content": str(result)[:800]}),
            "failureReason": reason or "",
            "immutableItems": validation.get("immutableItems") or [],
        }

        if (self.api_config or {}).get("taskUseMock"):
            return {
                "shouldAdjust": False,
                "immutableImpacted": False,
                "reasoning": "Mock mode: Step-B review skipped.",
                "proposedValidationCriteria": active,
                "patchSummary": "",
                "source": "step-b-agent",
            }

        try:
            reviewed = await runner_mod.review_contract_adjustment(
                packet,
                api_config=self.api_config,
                abort_event=self.abort_event,
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

    async def _retry_or_fail(
        self,
        *,
        task: Dict[str, Any],
        phase: str,
        error: str,
        decision: Optional[Dict[str, Any]] = None,
    ) -> None:
        runner_mod = _runner_module()
        task_id = str(task.get("task_id") or "")
        attempt = self._next_retry_attempt(task_id)
        last_retry_attempt = int(self.task_last_retry_attempt.get(task_id) or 0)
        duplicate_retry_attempt = attempt <= last_retry_attempt
        will_retry = attempt < self.MAX_RETRY_ATTEMPTS and not duplicate_retry_attempt

        payload = {
            "taskId": task_id,
            "phase": phase,
            "attempt": attempt,
            "maxAttempts": self.MAX_RETRY_ATTEMPTS,
            "willRetry": will_retry,
            "error": error,
            "decision": decision or {},
        }
        self._emit("task-error", payload)
        await self._record_task_attempt_failure(
            task_id=task_id,
            phase=phase,
            attempt=attempt,
            will_retry=will_retry,
            error=error,
            decision=decision,
        )
        await self._append_step_event(task_id, "task-error", payload)

        async with self._worker_lock:
            runner_mod.worker_manager["release_worker_by_task_id"](task_id)
        self._broadcast_worker_states()

        self.running_tasks.discard(task_id)

        if not will_retry:
            self.pending_tasks.discard(task_id)
            self._update_task_status(task_id, "failed")
            await self._trigger_fail_fast(
                failed_task_id=task_id,
                phase=phase,
                reason=error,
            )
            return

        self.task_last_retry_attempt[task_id] = attempt
        next_attempt = attempt + 1
        self.task_run_attempt[task_id] = next_attempt
        self.task_forced_attempt[task_id] = next_attempt
        self.task_next_attempt_hint[task_id] = max(int(self.task_next_attempt_hint.get(task_id) or 0), next_attempt)

        self.pending_tasks.add(task_id)
        self._update_task_status(task_id, "undone")

        retry_payload = {
            "taskId": task_id,
            "phase": phase,
            "attempt": attempt,
            "nextAttempt": next_attempt,
            "maxAttempts": self.MAX_RETRY_ATTEMPTS,
            "error": error,
            "decision": decision or {},
        }
        self._emit("attempt-retry", retry_payload)
        await self._append_step_event(task_id, "attempt-retry", retry_payload)

        self._spawn_task_execution(task)

    def _get_ready_tasks(self) -> List[Dict]:
        ready: List[Dict] = []
        for task in self.chain_cache:
            task_id = task["task_id"]
            if task_id in self.completed_tasks or task_id in self.running_tasks:
                continue
            if task_id not in self.pending_tasks:
                continue
            if self._are_dependencies_satisfied(task):
                ready.append(task)
        return ready

    async def _execute_tasks(self) -> None:
        self.is_running = True

        initial_ready = self._get_ready_tasks()
        logger.info(
            "Execution scheduling start idea_id={} plan_id={} initial_ready={} total={} ready_ids={}",
            self.idea_id,
            self.plan_id,
            len(initial_ready),
            len(self.chain_cache),
            [t.get("task_id") for t in initial_ready],
        )
        for task in initial_ready:
            self._spawn_task_execution(task)

        last_heartbeat = time.monotonic()
        while self.is_running and (len(self.completed_tasks) < len(self.chain_cache) or len(self.running_tasks) > 0):
            dependency_gap = self._find_dependency_gap()
            if dependency_gap:
                await self._trigger_fail_fast(
                    failed_task_id=dependency_gap.get("taskId") or "unknown",
                    phase="dependency",
                    reason=(
                        "Dependency resolution gap: dependency "
                        f"{dependency_gap.get('dependencyId')} for task "
                        f"{dependency_gap.get('taskId')} is in neither todo nor completed lists"
                    ),
                )
                break

            ready = self._get_ready_tasks()
            for task in ready:
                self._spawn_task_execution(task)

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
