"""
Generate execution from plan: extract atomic tasks, resolve dependencies, recompute stages.
Business logic: plan → execution for db storage.
"""

from typing import Dict, List, Set

from shared.graph import get_ancestor_chain, get_parent_id, compute_task_stages


def _is_atomic(task: Dict) -> bool:
    """Task is atomic if it has both input and output (formatted by Plan Agent)."""
    return bool(task.get("input") and task.get("output"))


def _get_atomic_descendants(task_id: str, atomic_ids: Set[str]) -> List[str]:
    """Find all atomic task_ids that are descendants of task_id in the decomposition tree."""
    prefix = task_id + "_"
    return [aid for aid in atomic_ids if aid.startswith(prefix)]


def _resolve_deps_for_atomic(all_tasks: List[Dict], atomic_tasks: List[Dict]) -> List[Dict]:
    """
    Resolve execution dependencies for atomic tasks.

    For each atomic task:
      1. Collect own sibling deps + inherited ancestor deps (cross-subtree).
      2. For each dep target: if atomic, keep; if non-atomic, replace with its atomic descendants.
    """
    task_map = {t["task_id"]: t for t in all_tasks if t.get("task_id")}
    atomic_ids = {t["task_id"] for t in atomic_tasks}

    result = []
    for t in atomic_tasks:
        tid = t["task_id"]

        collected_deps: Set[str] = set()
        for d in t.get("dependencies") or []:
            if d and isinstance(d, str):
                collected_deps.add(d)

        for ancestor_id in get_ancestor_chain(tid):
            ancestor = task_map.get(ancestor_id)
            if not ancestor:
                continue
            for d in ancestor.get("dependencies") or []:
                if d and isinstance(d, str):
                    collected_deps.add(d)

        resolved: Set[str] = set()
        for dep_id in collected_deps:
            if dep_id == tid:
                continue
            if dep_id in atomic_ids:
                resolved.add(dep_id)
            else:
                for ad in _get_atomic_descendants(dep_id, atomic_ids):
                    if ad != tid:
                        resolved.add(ad)

        result.append({**t, "dependencies": sorted(resolved)})

    return result


def build_execution_from_plan(plan: Dict) -> Dict:
    """
    Extract atomic tasks from plan, resolve dependencies, recompute stages.
    Returns execution dict with tasks (each has status: "undone").
    """
    all_tasks = plan.get("tasks") or []
    if not all_tasks:
        return {"tasks": []}

    atomic_tasks = [t for t in all_tasks if _is_atomic(t)]
    if not atomic_tasks:
        return {"tasks": []}

    resolved = _resolve_deps_for_atomic(all_tasks, atomic_tasks)
    staged = compute_task_stages(resolved)
    flat = []
    for stage_list in staged:
        for task in stage_list:
            flat.append({**task, "status": "undone"})
    return {"tasks": flat}
