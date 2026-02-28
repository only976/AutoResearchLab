"""
Graph utilities for task dependencies and task_id hierarchy.
Shared by plan (business logic) and visualization (layout).
"""

from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx


def get_parent_id(task_id: str) -> str:
    """Get parent task_id. E.g. '1_2' -> '1', '1' -> '0'."""
    if "_" in task_id:
        return task_id.rsplit("_", 1)[0]
    return "0"


def get_ancestor_chain(task_id: str) -> List[str]:
    """Return ancestor ids from immediate parent up to root, e.g. '1_2_3' -> ['1_2', '1', '0']."""
    chain = []
    curr = task_id
    while True:
        parent = get_parent_id(curr)
        chain.append(parent)
        if parent == "0":
            break
        curr = parent
    return chain


def get_ancestor_path(task_id: str) -> str:
    """Build ancestor path string, e.g. '1_2' -> '0 → 1 → 1_2'."""
    if not task_id:
        return ""
    parts = []
    curr = task_id
    while True:
        parts.insert(0, curr)
        if curr == "0":
            break
        curr = get_parent_id(curr)
    return " → ".join(parts)


def natural_task_id_key(tid: str) -> Tuple:
    """Sort key: '1' < '1_1' < '1_2' < '1_10'."""
    parts = tid.split("_")
    return tuple(int(p) if p.isdigit() else p for p in parts)


def build_dependency_graph(tasks: List[Dict[str, Any]], ids: Optional[Set[str]] = None) -> nx.DiGraph:
    """Build dependency graph from tasks. ids: if provided, only include nodes in ids."""
    ids = ids or {t["task_id"] for t in (tasks or []) if t.get("task_id")}
    G = nx.DiGraph()
    for t in tasks or []:
        tid = t.get("task_id")
        if not tid or tid not in ids:
            continue
        G.add_node(tid)
        for dep in t.get("dependencies") or []:
            if dep in ids and dep != tid:
                G.add_edge(dep, tid)
    return G


def _reduce_dependencies(G: nx.DiGraph, stages: List[List[Dict]]) -> List[List[Dict]]:
    """
    Transitive reduction: remove edges that are implied by other paths.
    E.g. if A→B→C exists, the direct edge A→C is redundant and removed.
    """
    G_reduced = nx.transitive_reduction(G)
    reduced_edges = set(G_reduced.edges())
    return [
        [
            {**t, "dependencies": [d for d in t.get("dependencies", []) if (d, t["task_id"]) in reduced_edges]}
            for t in stage
        ]
        for stage in stages
    ]


def compute_task_stages(
    tasks: List[Dict],
    reduce: bool = False,
) -> List[List[Dict]]:
    """
    Compute staged format from flat task list. No old stage data used.

    reduce=True:  display/tree view — transitive reduction, minimal edges.
    reduce=False: execution scheduling — keep all deps as-is.

    Returns [[stage0_tasks], [stage1_tasks], ...], each task has stage (1-based).
    """
    if not tasks or not isinstance(tasks, list) or len(tasks) == 0:
        return []

    task_list = [
        {**t, "task_id": t.get("task_id") or str(idx + 1), "dependencies": list(t.get("dependencies") or [])}
        for idx, t in enumerate(tasks)
    ]
    task_by_id = {t["task_id"]: t for t in task_list}

    G = build_dependency_graph(task_list)

    if not nx.is_directed_acyclic_graph(G):
        raise ValueError("Circular dependency detected in task graph")

    stages: List[List[Dict]] = []
    for level in nx.topological_generations(G):
        stage_tasks = [task_by_id[nid] for nid in level if nid in task_by_id]
        if stage_tasks:
            stages.append([{**t} for t in stage_tasks])

    final_stages = _reduce_dependencies(G, stages) if reduce else stages

    return [
        [{**task, "stage": idx + 1} for task in stage]
        for idx, stage in enumerate(final_stages)
    ]
