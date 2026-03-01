"""
Build treeData for display. Plan.tasks is the single source.

Pipeline (each run, no old stage reused):
  1. Extract: task_id, dependencies (never stage)
  2. Stage: topological sort + transitive reduction (minimal edges, wide parallel layout)
  3. Enrich: merge full task info
"""

from typing import List, Dict

from shared.graph import compute_task_stages


def extract_cache_from_tasks(tasks: List[Dict]) -> List[Dict]:
    """Extract task_id, dependencies. Never stage (always recompute)."""
    if not tasks or not isinstance(tasks, list):
        return []
    return [
        {
            "task_id": t.get("task_id") or "",
            "dependencies": list(t.get("dependencies") or []),
        }
        for t in tasks
        if t.get("task_id")
    ]


def enrich_tree_data(staged: List[List[Dict]], full_tasks: List[Dict]) -> List[Dict]:
    by_id = {t["task_id"]: t for t in (full_tasks or []) if t.get("task_id")}
    result = []
    for stage in staged:
        for c in stage:
            full = by_id.get(c["task_id"], {})
            result.append({**full, **c})
    return result


def build_tree_data(tasks: List[Dict]) -> List[Dict]:
    """
    Build treeData for display. Never uses old stage.
    Transitive reduction removes redundant edges while preserving parallelism.
    """
    if not tasks or len(tasks) == 0:
        return []
    cache = extract_cache_from_tasks(tasks)
    staged = compute_task_stages(cache, reduce=True)
    return enrich_tree_data(staged, tasks)
