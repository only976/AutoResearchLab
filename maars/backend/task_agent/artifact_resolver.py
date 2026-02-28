"""
Artifact resolution: load input artifacts from dependency tasks.
"""

from typing import Any, Dict, List

from db import get_task_artifact


class MissingDependencyArtifactError(Exception):
    """Raised when a task depends on another task's output that is not yet available."""

    def __init__(self, task_id: str, missing_deps: List[str], message: str = ""):
        self.task_id = task_id
        self.missing_deps = missing_deps
        super().__init__(message or f"Task {task_id} depends on outputs not ready: {missing_deps}")


async def resolve_artifacts(
    task: Dict[str, Any],
    task_map: Dict[str, Dict],
    plan_id: str,
) -> Dict[str, Any]:
    """
    Resolve input artifacts from dependency tasks.
    For each dep_id in task.dependencies, load the dep's output artifact from db.
    Returns { artifact_name: value }.
    Raises MissingDependencyArtifactError if any required artifact is missing.
    """
    deps = task.get("dependencies") or []
    if not deps:
        return {}

    result: Dict[str, Any] = {}
    missing: List[str] = []
    for dep_id in deps:
        dep_task = task_map.get(dep_id)
        if not dep_task:
            continue
        output_spec = dep_task.get("output") or {}
        artifact_name = output_spec.get("artifact")
        if not artifact_name:
            continue
        value = await get_task_artifact(plan_id, dep_id)
        if value is not None:
            result[artifact_name] = value
        else:
            missing.append(f"{dep_id} (artifact: {artifact_name})")

    if missing:
        raise MissingDependencyArtifactError(
            task.get("task_id", "?"),
            missing,
            f"Task {task.get('task_id', '?')} depends on outputs not ready: {missing}",
        )
    return result
