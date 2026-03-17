"""Single-task execution helpers for Task ExecutionRunner."""

import asyncio
import json
import random
import time
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger
from db import get_execution_task_step_dir


def _runner_module():
    from . import runner as runner_mod

    return runner_mod


class RunnerTaskExecutionMixin:
    @staticmethod
    def _write_text_file(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    async def _persist_attempt_prompt_snapshot(
        self,
        *,
        task_id: str,
        attempt: int,
        prompt_payload: Dict[str, Any],
    ) -> None:
        if not self.execution_run_id or not task_id:
            return
        try:
            step_dir = get_execution_task_step_dir(self.execution_run_id, task_id).resolve()
            step_dir.mkdir(parents=True, exist_ok=True)
            prompt_md_path = step_dir / f"prompt_attempt_{int(attempt)}.md"
            prompt_json_path = step_dir / f"prompt_attempt_{int(attempt)}.json"

            system_prompt = str(prompt_payload.get("systemPrompt") or "")
            user_message = str(prompt_payload.get("userMessage") or "")
            context_budget = prompt_payload.get("contextBudget") or {}
            compression = prompt_payload.get("compression") or {}

            combined_markdown = (
                f"# Task Prompt Snapshot\n\n"
                f"- Task ID: {task_id}\n"
                f"- Attempt: {int(attempt)}\n"
                f"- Run ID: {self.execution_run_id}\n\n"
                f"## System Prompt\n\n"
                f"```text\n{system_prompt}\n```\n\n"
                f"## User Message\n\n"
                f"```text\n{user_message}\n```\n\n"
                f"## Context Budget\n\n"
                f"```json\n{json.dumps(context_budget, ensure_ascii=False, indent=2)}\n```\n\n"
                f"## Compression Meta\n\n"
                f"```json\n{json.dumps(compression, ensure_ascii=False, indent=2)}\n```\n"
            )

            await asyncio.to_thread(self._write_text_file, prompt_md_path, combined_markdown)
            await asyncio.to_thread(
                self._write_text_file,
                prompt_json_path,
                json.dumps(
                    {
                        "taskId": task_id,
                        "attempt": int(attempt),
                        "runId": self.execution_run_id,
                        "prompt": prompt_payload,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            preview = (user_message or "")
            if len(preview) > 6000:
                preview = preview[:6000] + "\n...[truncated for UI; full prompt saved to step file]"
            front_chunk = (
                f"Prompt snapshot for attempt {int(attempt)} saved to {prompt_md_path.name}.\n"
                f"Please ensure this attempt does not repeat last failure patterns.\n\n"
                f"--- Prompt Preview (User Message) ---\n{preview}"
            )
            self._emit("task-thinking", {
                "taskId": task_id,
                "attempt": int(attempt),
                "operation": "PromptInit",
                "source": "task",
                "chunk": front_chunk,
            })
            await self._append_step_event(task_id, "task-prompt", {
                "attempt": int(attempt),
                "promptMarkdown": prompt_md_path.name,
                "promptJson": prompt_json_path.name,
                "promptChars": len(system_prompt) + len(user_message),
            })
        except Exception:
            logger.exception("Failed to persist prompt snapshot task_id={} attempt={}", task_id, attempt)

    async def _execute_task(self, task: Dict) -> None:
        runner_mod = _runner_module()
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
                slot_id = runner_mod.worker_manager["assign_task"](task["task_id"])
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
            self.running_tasks.discard(task["task_id"])
            self.pending_tasks.discard(task["task_id"])
            self._update_task_status(task["task_id"], "failed")
            await self._trigger_fail_fast(
                failed_task_id=task["task_id"],
                phase="scheduling",
                reason=f"Failed to acquire worker slot after {retry_count} retries",
            )
            return

        self.running_tasks.add(task["task_id"])
        logger.info("Task acquired worker task_id={} slot_id={}", task["task_id"], slot_id)
        self._update_task_status(task["task_id"], "doing")
        self._broadcast_worker_states()
        task_id = task["task_id"]
        run_attempt = self._resolve_run_attempt(task_id)
        reserved_attempt = self._reserve_execute_attempt(task_id, run_attempt)
        if reserved_attempt != run_attempt:
            logger.warning(
                "Duplicate execute launch blocked task_id={} requested_attempt={} reserved_attempt={}",
                task_id,
                run_attempt,
                reserved_attempt,
            )
            run_attempt = reserved_attempt
            self.task_run_attempt[task_id] = run_attempt
            self.task_forced_attempt[task_id] = run_attempt
            self.task_next_attempt_hint[task_id] = max(
                int(self.task_next_attempt_hint.get(task_id) or 0),
                run_attempt,
            )
        if run_attempt > 1:
            self.task_phase_failure_count[self._failure_key(task_id, "retry")] = max(
                self._get_failure_count(task_id, "retry"),
                run_attempt - 1,
            )

        self._emit("task-started", {
            "taskId": task["task_id"],
            "attempt": run_attempt,
            "title": task.get("description", task["task_id"]),
            "description": task.get("description", ""),
            "dependencies": task.get("dependencies") or [],
            "inputKeys": list((task.get("input") or {}).keys()),
            "outputKeys": list((task.get("output") or {}).keys()),
        })
        await self._append_step_event(task["task_id"], "task-started", {
            "attempt": run_attempt,
            "description": task.get("description", ""),
            "dependencies": task.get("dependencies") or [],
        })

        try:
            input_spec = task.get("input") or {}
            output_spec = task.get("output") or {}
            resolved_inputs: Dict[str, Any] = {}
            result: Any = None
            if not output_spec:
                raise ValueError(f"Task {task['task_id']} has no output spec")
            execution_error_message = ""
            try:
                resolved_inputs = await runner_mod.resolve_artifacts(task, self.task_map, self.idea_id or "", self.plan_id or "")
                logger.info(
                    "Task resolved inputs task_id={} input_keys={} output_keys={}",
                    task["task_id"],
                    sorted(list((resolved_inputs or {}).keys())) if isinstance(resolved_inputs, dict) else type(resolved_inputs).__name__,
                    sorted(list((output_spec or {}).keys())),
                )

                async def _on_thinking(chunk: str, task_id: Optional[str] = None, operation: Optional[str] = None, schedule_info: Optional[dict] = None) -> None:
                    active_task_id = task_id or task["task_id"]
                    thinking_attempt = run_attempt if active_task_id == task["task_id"] else self._get_current_attempt(active_task_id)
                    payload: dict = {
                        "chunk": chunk,
                        "source": "task",
                        "taskId": task_id,
                        "operation": operation or "Execute",
                        "attempt": thinking_attempt,
                    }
                    if schedule_info is not None:
                        payload["scheduleInfo"] = {**schedule_info, "attempt": thinking_attempt}
                    await self._emit_await("task-thinking", payload)
                    if task_id and chunk:
                        await self._append_step_event(task_id, "task-thinking", {
                            "attempt": thinking_attempt,
                            "operation": operation or "Execute",
                            "chunk": chunk,
                            "scheduleInfo": {**(schedule_info or {}), "attempt": thinking_attempt},
                        })

                api_cfg = self.api_config or {}
                task_container_name = ""
                execution_context = self._build_task_execution_context(task, resolved_inputs)
                if api_cfg.get("taskAgentMode"):
                    if not (self.idea_id and self.plan_id):
                        raise ValueError("Docker task execution requires idea_id and plan_id")
                    runtime = await runner_mod.ensure_execution_container(
                        execution_run_id=self.execution_run_id,
                        idea_id=self.idea_id,
                        plan_id=self.plan_id,
                        task_id=task["task_id"],
                        skills_dir=runner_mod.SKILLS_ROOT,
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
                    async def _on_prompt_built(prompt_payload: Dict[str, Any]) -> None:
                        await self._persist_attempt_prompt_snapshot(
                            task_id=task["task_id"],
                            attempt=run_attempt,
                            prompt_payload=prompt_payload,
                        )

                    result = await runner_mod.run_task_agent(
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
                        on_prompt_built=_on_prompt_built,
                    )
                else:
                    result = await runner_mod.execute_task(
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
                await runner_mod.save_task_artifact(self.idea_id or "", self.plan_id or "", task["task_id"], to_save)
                self._emit("task-output", {"taskId": task["task_id"], "attempt": run_attempt, "output": result})
                await self._append_step_event(task["task_id"], "task-output", {"attempt": run_attempt, "output": to_save})
                execution_passed = True
            except Exception as exec_err:
                logger.exception("LLM execution failed for task {}", task["task_id"])
                execution_error_message = str(exec_err)
                await self._append_step_event(task["task_id"], "task-execution-error", {"error": execution_error_message})
                execution_passed = False

            if not execution_passed:
                self._update_task_status(task["task_id"], "execution-failed")
                await self._retry_or_fail(
                    task=task,
                    phase="execution",
                    error=execution_error_message or "Task execution failed",
                    decision={"action": "retry", "source": "simple-retry"},
                )
                return

            runner_mod.worker_manager["set_worker_status"](task["task_id"], "validating")
            self._broadcast_worker_states()
            self._update_task_status(task["task_id"], "validating")

            task_id = task["task_id"]
            output_spec = task.get("output") or {}
            use_mock = (self.api_config or {}).get("taskUseMock", True)
            original_criteria = self._get_original_validation_criteria(task)
            if use_mock:
                validation_passed = random.random() < self.VALIDATION_PASS_PROBABILITY
                report = (
                    f"# Validating Task {task_id}\n\n"
                    "Checking output against simplified 3-step flow...\n\n"
                    "- Step A format gate: PASS\n"
                    "- Step B contract review: SKIPPED (mock mode)\n"
                    "- Step C original-contract validation: PASS\n\n"
                    f"**Result: {'PASS' if validation_passed else 'FAIL'}**\n\n"
                    "(Mock validation mode)"
                )
                step_b_review = {
                    "shouldAdjust": False,
                    "immutableImpacted": False,
                    "reasoning": "Mock mode: Step-B review skipped.",
                    "patchSummary": "",
                    "source": "step-b-agent",
                }
            else:
                format_passed, format_report = self._run_step_a_structural_format_gate(result, output_spec)

                step_b_review = await self._run_step_b_contract_review(
                    task=task,
                    result=result,
                    reason=format_report,
                    output_format=output_spec.get("format") or "",
                    on_thinking=_on_thinking,
                )
                self._emit("task-step-b", {
                    "taskId": task_id,
                    "attempt": self._get_failure_count(task_id, "retry") + 1,
                    "phase": "validation",
                    "shouldAdjust": bool(step_b_review.get("shouldAdjust")),
                    "immutableImpacted": bool(step_b_review.get("immutableImpacted")),
                    "equivalenceCheckRequired": bool(step_b_review.get("equivalenceCheckRequired")),
                    "equivalenceCheckHint": step_b_review.get("equivalenceCheckHint") or "",
                    "reasoning": step_b_review.get("reasoning") or "",
                    "patchSummary": step_b_review.get("patchSummary") or "",
                })
                await self._append_step_event(task_id, "task-step-b", {
                    "shouldAdjust": bool(step_b_review.get("shouldAdjust")),
                    "immutableImpacted": bool(step_b_review.get("immutableImpacted")),
                    "equivalenceCheckRequired": bool(step_b_review.get("equivalenceCheckRequired")),
                    "equivalenceCheckHint": step_b_review.get("equivalenceCheckHint") or "",
                    "reasoning": step_b_review.get("reasoning") or "",
                    "patchSummary": step_b_review.get("patchSummary") or "",
                })

                if not format_passed:
                    validation_passed = False
                    _step_a_reason = self._extract_direct_fail_reason(format_report)
                    report = (
                        "# Validation FAILED\n\n"
                        "Step A (format gate) failed.\n\n"
                        f"{format_report}\n\n"
                        f"DIRECT_REASON: {_step_a_reason}"
                    )
                else:
                    # Step C should validate against the active contract after Step-B review.
                    # Fallback to original criteria only when no active criteria exist.
                    active_criteria = list(((task.get("validation") or {}).get("criteria") or []))
                    final_validation_spec = {"criteria": active_criteria or list(original_criteria)}
                    validation_context = {
                        "globalGoal": self._idea_text or "",
                        "taskDescription": task.get("description") or "",
                        "attempt": run_attempt,
                        "attemptHistory": list(self.task_attempt_history.get(task_id) or []),
                        "inputArtifacts": sorted(list((resolved_inputs or {}).keys())),
                    }
                    validation_passed, final_report = await runner_mod.validate_task_output_with_llm(
                        result,
                        output_spec,
                        task_id,
                        validation_spec=final_validation_spec,
                        validation_context=validation_context,
                        api_config=self.api_config,
                        abort_event=self.abort_event,
                        on_thinking=_on_thinking,
                    )
                    _step_c_reason = self._extract_direct_fail_reason(final_report) if not validation_passed else ""
                    _direct_line = f"\n\nDIRECT_REASON: {_step_c_reason}" if _step_c_reason else ""
                    report = (
                        "# Validation Flow\n\n"
                        "Step A (format gate): PASS\n"
                        f"Step B (contract review): {'ADJUSTED' if step_b_review.get('shouldAdjust') else 'NO CHANGE'}\n"
                        "Step C (original contract): "
                        f"{'PASS' if validation_passed else 'FAIL'}\n\n"
                        f"{final_report}"
                        f"{_direct_line}"
                    )
            if use_mock:
                for chunk in runner_mod.chunk_string(report, 20):
                    await self._emit_await("task-thinking", {"chunk": chunk, "source": "task", "taskId": task_id, "operation": "Validate"})
                    await asyncio.sleep(runner_mod._MOCK_VALIDATOR_CHUNK_DELAY)

            if use_mock:
                self._emit("task-step-b", {
                    "taskId": task_id,
                    "attempt": self._get_failure_count(task_id, "retry") + 1,
                    "phase": "validation",
                    "shouldAdjust": False,
                    "immutableImpacted": False,
                    "reasoning": step_b_review.get("reasoning") or "Mock mode: Step-B skipped.",
                    "patchSummary": "",
                })
                await self._append_step_event(task_id, "task-step-b", {
                    "shouldAdjust": False,
                    "immutableImpacted": False,
                    "reasoning": step_b_review.get("reasoning") or "Mock mode: Step-B skipped.",
                    "patchSummary": "",
                })

            if self.idea_id and self.plan_id:
                await runner_mod.save_validation_report(
                    self.idea_id,
                    self.plan_id,
                    task_id,
                    {"passed": validation_passed, "report": report},
                )

            report_text = str(report or "").strip()
            direct_reason = "All required validation checks passed." if validation_passed else "Validation checks failed."
            if not validation_passed and report_text:
                for line in report_text.splitlines():
                    s = line.strip()
                    if s.upper().startswith("DIRECT_REASON:"):
                        direct_reason = s[len("DIRECT_REASON:"):].strip()
                        break
                else:
                    direct_reason = self._extract_direct_fail_reason(report_text)

            validation_summary = {
                "finalCheckResult": report_text[:1500],
                "expectedFormat": str(output_spec.get("format") or ""),
                "directReason": direct_reason,
                "stepB": {
                    "shouldAdjust": bool(step_b_review.get("shouldAdjust")),
                    "immutableImpacted": bool(step_b_review.get("immutableImpacted")),
                    "equivalenceCheckRequired": bool(step_b_review.get("equivalenceCheckRequired")),
                    "equivalenceCheckHint": str(step_b_review.get("equivalenceCheckHint") or ""),
                    "patchSummary": str(step_b_review.get("patchSummary") or ""),
                    "reasoning": str(step_b_review.get("reasoning") or ""),
                },
            }

            await self._append_step_event(task["task_id"], "task-validation", {
                "attempt": run_attempt,
                "passed": validation_passed,
                "report": report,
                "summary": validation_summary,
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
                    runner_mod.worker_manager["release_worker_by_task_id"](task["task_id"])
                self._broadcast_worker_states()

                self._emit("task-completed", {
                    "taskId": task["task_id"],
                    "attempt": run_attempt,
                    "validated": True,
                    "validationReport": report[:500] if report else "",
                    "validationSummary": validation_summary,
                    "status": "done",
                })
                await self._append_step_event(task["task_id"], "task-completed", {
                    "attempt": run_attempt,
                    "validated": True,
                    "validationSummary": validation_summary,
                    "status": "done",
                })
            else:
                self._update_task_status(task["task_id"], "validation-failed")
                validation_reason = "Validation failed"
                if report:
                    validation_reason = report[:500]
                await self._retry_or_fail(
                    task=task,
                    phase="validation",
                    error=validation_reason,
                    decision={
                        "action": "retry",
                        "source": "simple-retry",
                        "stepB": step_b_review,
                        "validationSummary": validation_summary,
                    },
                )
                return

        except Exception as e:
            async with self._worker_lock:
                runner_mod.worker_manager["release_worker_by_task_id"](task["task_id"])
            self._broadcast_worker_states()
            await self._append_step_event(task["task_id"], "task-error", {"error": str(e)})
            raise
        finally:
            task_container_name = self.task_docker_containers.pop(task["task_id"], "")
            if task_container_name:
                try:
                    await runner_mod.stop_execution_container(task_container_name)
                except Exception:
                    logger.exception("Failed to stop Docker task container task_id={} container={}", task["task_id"], task_container_name)
            if self.docker_container_name == task_container_name:
                self.docker_container_name = ""

        self.running_tasks.discard(task["task_id"])
        self.completed_tasks.add(task["task_id"])
        self.pending_tasks.discard(task["task_id"])
        self._update_task_status(task["task_id"], "done")
        self._clear_task_failure_counts(task["task_id"])
        self.task_last_retry_attempt.pop(task["task_id"], None)
        self.task_run_attempt.pop(task["task_id"], None)
        self.task_forced_attempt.pop(task["task_id"], None)
        self.task_next_attempt_hint.pop(task["task_id"], None)
        self.task_execute_started_attempts.pop(task["task_id"], None)
        self.task_attempt_history.pop(task["task_id"], None)
        if self.research_id:
            await runner_mod.delete_task_attempt_memories(self.research_id, task["task_id"])
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
        runner_mod = _runner_module()
        api_cfg = self.api_config or {}
        if not api_cfg.get("reflectionEnabled", False):
            return
        if api_cfg.get("taskUseMock", False):
            return
        try:
            evaluation = await runner_mod.self_evaluate(
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
                skill_content = await runner_mod.generate_skill_from_reflection(
                    "task", evaluation,
                    context={"task_id": task["task_id"], "description": task.get("description", "")},
                    api_config=api_cfg, abort_event=self.abort_event,
                )
                if skill_content:
                    runner_mod.save_learned_skill("task", suggestion["name"], skill_content)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Task reflection failed for %s: %s", task["task_id"], e)
