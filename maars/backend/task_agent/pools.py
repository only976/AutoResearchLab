"""
Concurrency pool - limits max concurrent task execution.
Max concurrency from settings; no worker slots.
"""

from typing import Dict, Optional

_DEFAULT_MAX = 7
_slots_in_use = 0
_max_concurrency = _DEFAULT_MAX
_task_status: Dict[str, str] = {}  # task_id -> "busy" | "validating"


def initialize(max_concurrency: int = _DEFAULT_MAX) -> None:
    """Reset pool with new max. Call at execution start."""
    global _slots_in_use, _max_concurrency, _task_status
    _task_status.clear()
    _slots_in_use = 0
    _max_concurrency = max(1, int(max_concurrency))


def assign_task(task_id: str) -> Optional[str]:
    """Acquire a slot. Returns task_id on success, None if at capacity."""
    global _slots_in_use
    if _slots_in_use >= _max_concurrency:
        return None
    _slots_in_use += 1
    _task_status[task_id] = "busy"
    return task_id


def release_by_task_id(task_id: str) -> Optional[str]:
    """Release slot for task_id. Returns task_id if released."""
    global _slots_in_use
    if task_id in _task_status:
        del _task_status[task_id]
        _slots_in_use -= 1
        return task_id
    return None


def set_task_status(task_id: str, status: str) -> None:
    """Set task status: busy | validating."""
    if task_id in _task_status:
        _task_status[task_id] = status


def get_stats() -> Dict:
    """Return {busy, validating, max}."""
    busy = sum(1 for s in _task_status.values() if s == "busy")
    validating = sum(1 for s in _task_status.values() if s == "validating")
    return {
        "busy": busy,
        "validating": validating,
        "max": _max_concurrency,
    }


# Runner compatibility
worker_manager = {
    "assign_task": assign_task,
    "release_worker_by_task_id": release_by_task_id,
    "set_worker_status": set_task_status,
    "get_worker_stats": get_stats,
    "initialize_workers": initialize,
}
