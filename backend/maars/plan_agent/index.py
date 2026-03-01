"""
Plan Agent - atomicity check, decompose, format flow.
(Atomicity = check if task is atomic; output validation is in Task Agent phase.)
Multi Agent: Plan Agent (plan_agent) + Task Agent (task_agent).
LLM implementation: plan_agent/llm/
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional

from shared.graph import get_ancestor_path, get_parent_id

from .agent import run_plan_agent
from .agent_tools import _find_task_idx
from .llm.executor import assess_quality, check_atomicity, decompose_task, format_task, raise_if_aborted


async def _atomicity_and_decompose_recursive(
    task: Dict,
    all_tasks: List[Dict],
    on_task: Optional[Callable[[Dict], None]],
    on_thinking: Callable[[str], None],
    depth: int,
    check_aborted: Callable[[], bool],
    abort_event: Optional[Any],
    on_tasks_batch: Optional[Callable[[List[Dict], Dict, List[Dict]], None]] = None,
    idea: Optional[str] = None,
    use_mock: bool = False,
    api_config: Optional[Dict] = None,
    plan_id: Optional[str] = None,
) -> None:
    if check_aborted and check_aborted():
        raise asyncio.CancelledError("Aborted")

    pid = task["task_id"]
    siblings = [t for t in all_tasks if t.get("task_id") != pid and get_parent_id(t.get("task_id", "")) == get_parent_id(pid)]
    atomicity_context = {
        "depth": depth,
        "ancestor_path": get_ancestor_path(pid),
        "idea": idea or "",
        "siblings": siblings,
    }
    v = await check_atomicity(task, on_thinking, abort_event, atomicity_context, use_mock, api_config, plan_id)
    atomic = v["atomic"]

    if atomic:
        io_result = await format_task(task, on_thinking, abort_event, use_mock, api_config, plan_id)
        if not io_result:
            raise ValueError(f"Format failed for atomic task {task['task_id']}: missing input/output")
        idx = _find_task_idx(all_tasks, task["task_id"])
        if idx >= 0:
            all_tasks[idx] = {**all_tasks[idx], **io_result}
        return

    children = await decompose_task(task, on_thinking, abort_event, all_tasks, idea, depth, use_mock, api_config, plan_id)
    if not children:
        raise ValueError(f"Decompose returned no children for task {task['task_id']}")

    all_tasks.extend(children)
    if on_tasks_batch:
        on_tasks_batch(children, task, list(all_tasks))
    elif on_task:
        for t in children:
            on_task(t)

    await asyncio.gather(*[
        _atomicity_and_decompose_recursive(
            child, all_tasks, on_task, on_thinking, depth + 1, check_aborted, abort_event, on_tasks_batch,
            idea, use_mock, api_config, plan_id,
        )
        for child in children
    ])


async def run_plan(
    plan: Dict,
    on_task: Optional[Callable[[Dict], None]],
    on_thinking: Callable[[str], None],
    abort_event: Optional[Any] = None,
    on_tasks_batch: Optional[Callable[[List[Dict], Dict, List[Dict]], None]] = None,
    use_mock: bool = False,
    api_config: Optional[Dict] = None,
    skip_quality_assessment: bool = False,
    plan_id: Optional[str] = None,
) -> Dict:
    """Run atomicity->decompose->format from root task, top-down to all atomic tasks. When planAgentMode=True, uses Plan Agent loop instead."""

    def check_aborted() -> bool:
        return abort_event is not None and abort_event.is_set()

    tasks = plan.get("tasks") or []
    root_task = next((t for t in tasks if t.get("task_id") == "0"), None)
    if not root_task:
        root_task = next(
            (t for t in tasks if t.get("task_id") and not (t.get("dependencies") or [])),
            tasks[0] if tasks else None,
        )
    if not root_task:
        raise ValueError("No decomposable task found. Generate plan first.")

    all_tasks = list(tasks)
    on_thinking_fn = on_thinking or (lambda *a, **_: None)
    idea = plan.get("idea") or root_task.get("description") or ""

    if api_config and api_config.get("planAgentMode"):
        await run_plan_agent(
            plan, on_thinking_fn, abort_event, on_tasks_batch,
            use_mock=use_mock, api_config=api_config, plan_id=plan_id,
        )
    else:
        await _atomicity_and_decompose_recursive(
            root_task, all_tasks, on_task, on_thinking_fn, 0, check_aborted, abort_event, on_tasks_batch,
            idea=idea, use_mock=use_mock, api_config=api_config, plan_id=plan_id,
        )
        plan["tasks"] = all_tasks
    if not skip_quality_assessment:
        raise_if_aborted(abort_event)
        quality = await assess_quality(plan, on_thinking_fn, abort_event, use_mock, api_config)
        plan["qualityScore"] = quality.get("score", 0)
        plan["qualityComment"] = quality.get("comment", "")
    else:
        plan["qualityScore"] = None
        plan["qualityComment"] = ""
    return {"tasks": all_tasks}
