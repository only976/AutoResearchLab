"""Retry/attempt helper functions for Task ExecutionRunner.

All functions are stateless module-level functions. State dictionaries
are passed explicitly, making dependencies visible and testable.
"""

import json
import re
from typing import Any, Dict, List, Set


def failure_key(task_id: str, bucket: str) -> str:
    return f"{task_id}:{bucket}"


def get_failure_count(phase_counts: Dict[str, int], task_id: str, bucket: str) -> int:
    return int(phase_counts.get(failure_key(task_id, bucket), 0) or 0)


def clear_task_failure_counts(
    phase_counts: Dict[str, int],
    task_id: str,
) -> None:
    prefix = f"{task_id}:"
    for key in list(phase_counts.keys()):
        if key.startswith(prefix):
            phase_counts.pop(key, None)


def extract_direct_fail_reason(report_text: str) -> str:
    """Return the single most helpful FAIL reason line from a validation report."""
    for line in report_text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        upper = s.upper()
        if ("FAIL" in upper or "FAILED" in upper) and re.search(r"FAIL\s*\(", s, re.IGNORECASE):
            return s.lstrip("-* ")
    for line in report_text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "FAIL" in s.upper() or "FAILED" in s.upper():
            return s.lstrip("-* ")
    for line in report_text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s
    return "Validation failed."


def next_retry_attempt(
    attempt_history: Dict[str, List[Dict]],
    phase_counts: Dict[str, int],
    task_id: str,
) -> int:
    history = attempt_history.get(task_id) or []
    history_attempts = 0
    for item in history:
        n = int(item.get("attempt") or 0)
        if n > history_attempts:
            history_attempts = n
    in_memory_attempts = get_failure_count(phase_counts, task_id, "retry")
    next_count = max(history_attempts, in_memory_attempts) + 1
    phase_counts[failure_key(task_id, "retry")] = next_count
    return next_count


def get_current_attempt(
    attempt_history: Dict[str, List[Dict]],
    phase_counts: Dict[str, int],
    task_id: str,
) -> int:
    history = attempt_history.get(task_id) or []
    history_attempts = 0
    for item in history:
        n = int(item.get("attempt") or 0)
        if n > history_attempts:
            history_attempts = n
    in_memory_attempts = get_failure_count(phase_counts, task_id, "retry")
    return max(history_attempts, in_memory_attempts) + 1


def resolve_run_attempt(
    task_run_attempt: Dict[str, int],
    task_forced_attempt: Dict[str, int],
    task_next_attempt_hint: Dict[str, int],
    attempt_history: Dict[str, List[Dict]],
    phase_counts: Dict[str, int],
    task_id: str,
) -> int:
    """Resolve a monotonic attempt number from all retry sources.

    Order is intentionally max-based to avoid regressions when one state source
    is stale (e.g. delayed events or transient resets).
    """
    explicit = int(task_run_attempt.get(task_id) or 0)
    baseline = get_current_attempt(attempt_history, phase_counts, task_id)
    forced = int(task_forced_attempt.get(task_id) or 0)
    hinted = int(task_next_attempt_hint.get(task_id) or 0)
    run_attempt = max(1, explicit, baseline, forced, hinted)
    task_run_attempt[task_id] = run_attempt
    task_next_attempt_hint[task_id] = run_attempt
    return run_attempt


def reserve_execute_attempt(
    started_attempts: Dict[str, Set[int]],
    task_id: str,
    requested_attempt: int,
) -> int:
    """Reserve a unique execute-attempt for this task in current run.

    Hard guard: one attempt number can launch execute ADK at most once.
    If a duplicate launch is requested, bump to the next free attempt.
    """
    attempt = max(1, int(requested_attempt or 1))
    seen = started_attempts.setdefault(task_id, set())
    while attempt in seen:
        attempt += 1
    seen.add(attempt)
    return attempt


def get_original_validation_criteria(task: Dict[str, Any]) -> List[str]:
    validation = task.setdefault("validation", {})
    if not isinstance(validation, dict):
        validation = {}
        task["validation"] = validation
    original = list(validation.get("originalCriteria") or [])
    current = list(validation.get("criteria") or [])
    if not original:
        original = list(current)
        validation["originalCriteria"] = list(original)
    return list(original)


def run_step_a_structural_format_gate(result: Any, output_spec: Dict[str, Any]) -> tuple[bool, str]:
    """Step A gate: only check structural completeness, never semantic correctness.

    This stage should answer: "Is the output structurally consumable?"
    It must not enforce business/content criteria, which belong to Step C.
    """
    expected_format = str((output_spec or {}).get("format") or "").strip()
    expected_lc = expected_format.lower()
    requires_structured = any(tok in expected_lc for tok in ("json", "dictionary", "dict", "object", "map"))

    if result is None:
        return False, "- Output structure: FAIL (missing output payload)"

    if isinstance(result, dict):
        if not result:
            return False, "- Output structure: FAIL (empty object)"
        return True, "- Output structure: PASS (non-empty object)"

    if isinstance(result, list):
        if not result:
            return False, "- Output structure: FAIL (empty list)"
        return True, "- Output structure: PASS (non-empty list)"

    if isinstance(result, str):
        text = result.strip()
        if not text:
            return False, "- Output structure: FAIL (empty string)"
        if requires_structured:
            try:
                parsed = json.loads(text)
            except Exception:
                return False, "- Output structure: FAIL (expected structured JSON text but parsing failed)"
            if isinstance(parsed, (dict, list)) and parsed:
                return True, "- Output structure: PASS (structured JSON text is parsable and non-empty)"
            return False, "- Output structure: FAIL (structured JSON text parsed but empty/invalid container)"
        return True, "- Output structure: PASS (non-empty text)"

    text = str(result).strip()
    if not text:
        return False, "- Output structure: FAIL (unreadable output)"
    return True, "- Output structure: PASS (stringifiable output)"
