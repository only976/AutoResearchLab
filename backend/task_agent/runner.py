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
from .runner_execution_mixin import RunnerExecutionMixin
from .runner_memory_mixin import RunnerMemoryMixin
from .runner_retry_mixin import RunnerRetryMixin
from .runner_state_mixin import RunnerStateMixin

# --- Backward-compat symbols for test monkeypatching ---
# Tests do: monkeypatch.setattr(runner_mod, "resolve_artifacts", fake)
# These imports keep those patches working until tests migrate to RunnerDeps injection.
from db import DB_DIR, delete_task_artifact, get_idea, save_execution, save_task_artifact, save_validation_report  # noqa: F401
from db import delete_task_attempt_memories, list_task_attempt_memories, save_task_attempt_memory  # noqa: F401
from shared.utils import chunk_string  # noqa: F401
from .artifact_resolver import resolve_artifacts  # noqa: F401
from .agent import run_task_agent  # noqa: F401
from .agent_tools import SKILLS_ROOT  # noqa: F401
from .pools import worker_manager  # noqa: F401
from .docker_runtime import ensure_execution_container, get_local_docker_status, prepare_execution_runtime, stop_execution_container  # noqa: F401
from .llm.executor import execute_task  # noqa: F401
from .llm.validation import validate_task_output_with_readonly_agent  # noqa: F401
from validate_agent import review_contract_adjustment  # noqa: F401
from shared.reflection import self_evaluate, generate_skill_from_reflection, save_learned_skill  # noqa: F401
validate_task_output_with_llm = validate_task_output_with_readonly_agent

def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default

_MOCK_VALIDATOR_CHUNK_DELAY = _env_float("MAARS_MOCK_VALIDATOR_CHUNK_DELAY", 0.03)


class ExecutionRunner(
    RunnerMemoryMixin,
    RunnerRetryMixin,
    RunnerStateMixin,
    RunnerExecutionMixin,
):
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


