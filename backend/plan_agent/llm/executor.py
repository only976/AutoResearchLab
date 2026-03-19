"""
Plan Agent 单轮 LLM 实现 - atomicity, decompose, format, quality.
Agent 实现放在 plan_agent/，单轮 LLM 放在 plan_agent/llm/。
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional

import networkx as nx
import json_repair

from db import save_ai_response
from shared.graph import build_dependency_graph, get_ancestor_path, get_parent_id
from shared.utils import extract_codeblock
from .executor_helpers import (
    _build_messages_for_context,
    _call_real_chat_completion,
    make_model_call,
)

from shared.constants import (
    MAX_FORMAT_REPAIR_ATTEMPTS,
    PLAN_MAX_VALIDATION_RETRIES,
    TEMP_AGENT_LOOP,
    TEMP_DETERMINISTIC,
    TEMP_RETRY,
    TEMP_STRUCTURED,
)
from shared.structured_output import generate_with_repair


async def real_chat_completion(
    *,
    messages: List[Dict[str, Any]],
    phase: str,
    on_thinking: Callable[[str], None],
    task_id: str,
    op_label: str,
    abort_event: Optional[Any],
    api_config: Optional[Dict] = None,
    temperature: float = TEMP_DETERMINISTIC,
) -> str:
    """Compatibility wrapper so tests can monkeypatch plan_exec.real_chat_completion."""
    return await _call_real_chat_completion(
        messages=messages,
        phase=phase,
        on_thinking=on_thinking,
        task_id=task_id,
        op_label=op_label,
        abort_event=abort_event,
        api_config=api_config,
        temperature=temperature,
    )


def _parse_json_response(text: str) -> Any:
    """Parse JSON from AI response using json_repair for malformed output."""
    cleaned = extract_codeblock(text) or (text or "").strip()
    try:
        return json_repair.loads(cleaned)
    except Exception as e:
        raise ValueError(f"Failed to parse JSON from AI response: {e}") from e


def _validate_atomicity_response(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    if "atomic" not in result:
        return False
    v = result["atomic"]
    return isinstance(v, bool) or v in (0, 1, "true", "false")


def _validate_decompose_response(result: Any, parent_id: str) -> tuple[bool, str]:
    if not isinstance(result, dict):
        return False, "Response is not a dict"
    tasks = result.get("tasks")
    if not isinstance(tasks, list) or len(tasks) == 0:
        return False, "tasks must be a non-empty list"
    seen_ids: set[str] = set()
    valid_prefix = parent_id if parent_id == "0" else f"{parent_id}_"
    for i, t in enumerate(tasks):
        if not isinstance(t, dict):
            return False, f"Task {i} is not a dict"
        tid = t.get("task_id")
        if not tid or not isinstance(tid, str):
            return False, f"Task {i} missing or invalid task_id"
        if tid in seen_ids:
            return False, f"Duplicate task_id: {tid}"
        seen_ids.add(tid)
        if parent_id == "0":
            if not tid.isdigit() or tid == "0":
                return False, f"Top-level task_id must be 1,2,3,... got {tid}"
        else:
            if not tid.startswith(valid_prefix) or tid == parent_id:
                return False, f"Child task_id must be {parent_id}_N, got {tid}"
        if not t.get("description") or not isinstance(t.get("description"), str):
            return False, f"Task {tid} missing or invalid description"
        deps = t.get("dependencies")
        if not isinstance(deps, list):
            return False, f"Task {tid} dependencies must be a list"
        for d in deps:
            if not isinstance(d, str):
                return False, f"Task {tid} has non-string dependency"
            if d == parent_id:
                return False, f"Task {tid} must not depend on parent {parent_id} (use task_id hierarchy instead)"
            if d and d not in seen_ids:
                return False, f"Task {tid} dependency {d} must be an earlier sibling"
    if seen_ids and not nx.is_directed_acyclic_graph(build_dependency_graph(tasks, ids=seen_ids)):
        return False, "Circular dependency detected among children"
    return True, ""


def raise_if_aborted(abort_event: Optional[Any]) -> None:
    """Raise CancelledError if abort_event is set."""
    if abort_event is not None and abort_event.is_set():
        raise asyncio.CancelledError("Aborted")


async def check_atomicity(
    task: Dict,
    on_thinking: Callable[[str], None],
    abort_event: Optional[Any],
    atomicity_context: Optional[Dict] = None,
    use_mock: bool = False,
    api_config: Optional[Dict] = None,
    idea_id: Optional[str] = None,
    plan_id: Optional[str] = None,
) -> Dict:
    """Check if task is atomic. Plan Agent LLM single-turn."""
    raise_if_aborted(abort_event)
    ctx: Dict[str, Any] = {"type": "atomicity", "taskId": task["task_id"], "task": task}
    if atomicity_context:
        ctx["atomicityContext"] = atomicity_context

    messages, _phase = _build_messages_for_context(ctx)
    model_call = make_model_call(
        context=ctx, on_thinking=on_thinking, abort_event=abort_event,
        use_mock=use_mock, api_config=api_config,
    )

    def _validate(parsed: Any) -> tuple[bool, str]:
        if not _validate_atomicity_response(parsed):
            return False, "Atomicity response invalid: missing or invalid atomic field"
        return True, ""

    result, _raw = await generate_with_repair(
        base_messages=messages,
        model_call=model_call,
        parse_fn=_parse_json_response,
        validate_fn=_validate,
        temperatures=[TEMP_DETERMINISTIC] + [TEMP_RETRY] * PLAN_MAX_VALIDATION_RETRIES,
    )

    out = {"atomic": bool(result.get("atomic"))}
    if idea_id and plan_id:
        asyncio.create_task(save_ai_response(
            idea_id, plan_id, "atomicity", task["task_id"],
            {"content": {"atomic": out["atomic"]}, "reasoning": ""},
        ))
    return out


async def decompose_task(
    parent_task: Dict,
    on_thinking: Callable[[str], None],
    abort_event: Optional[Any],
    all_tasks: List[Dict],
    idea: Optional[str] = None,
    depth: int = 0,
    use_mock: bool = False,
    api_config: Optional[Dict] = None,
    idea_id: Optional[str] = None,
    plan_id: Optional[str] = None,
) -> List[Dict]:
    """Decompose non-atomic task into children. Plan Agent LLM single-turn."""
    raise_if_aborted(abort_event)
    ctx: Dict[str, Any] = {"type": "decompose", "taskId": parent_task["task_id"], "task": parent_task}
    pid = parent_task["task_id"]
    siblings = [t for t in all_tasks if t.get("task_id") != pid and get_parent_id(t.get("task_id", "")) == get_parent_id(pid)]
    ctx["decomposeContext"] = {
        "idea": idea or "",
        "siblings": siblings,
        "depth": depth,
        "ancestor_path": get_ancestor_path(pid),
    }

    messages, _phase = _build_messages_for_context(ctx)
    model_call = make_model_call(
        context=ctx, on_thinking=on_thinking, abort_event=abort_event,
        use_mock=use_mock, api_config=api_config,
    )

    def _validate(parsed: Any) -> tuple[bool, str]:
        ok, err_msg = _validate_decompose_response(parsed, pid)
        return ok, err_msg or "Decompose validation failed"

    result, _raw = await generate_with_repair(
        base_messages=messages,
        model_call=model_call,
        parse_fn=_parse_json_response,
        validate_fn=_validate,
        temperatures=[TEMP_AGENT_LOOP] + [TEMP_RETRY] * PLAN_MAX_VALIDATION_RETRIES,
    )

    tasks = result.get("tasks") or []
    out = [
        t
        for t in tasks
        if t.get("task_id") and t.get("description") and isinstance(t.get("dependencies"), list)
    ]
    if idea_id and plan_id:
        asyncio.create_task(save_ai_response(
            idea_id, plan_id, "decompose", pid,
            {"content": {"tasks": tasks}, "reasoning": ""},
        ))
    return out


async def format_task(
    task: Dict,
    on_thinking: Callable[[str], None],
    abort_event: Optional[Any],
    use_mock: bool = False,
    api_config: Optional[Dict] = None,
    idea_id: Optional[str] = None,
    plan_id: Optional[str] = None,
) -> Optional[Dict]:
    """Generate input/output spec for atomic task. Plan Agent LLM single-turn with repair retries."""
    temps = [TEMP_STRUCTURED] + [TEMP_RETRY] * max(1, MAX_FORMAT_REPAIR_ATTEMPTS - 1)
    ctx = {"type": "format", "taskId": task.get("task_id", ""), "task": task}
    messages, _phase = _build_messages_for_context(ctx)
    model_call = make_model_call(
        context=ctx, on_thinking=on_thinking, abort_event=abort_event,
        use_mock=use_mock, api_config=api_config,
    )

    def _validate(parsed: Any) -> tuple[bool, str]:
        if not isinstance(parsed, dict):
            return False, "FormatTask response must be a JSON object"
        if not parsed.get("input") or not parsed.get("output"):
            return False, "FormatTask returned no input/output"
        return True, ""

    result, _raw = await generate_with_repair(
        base_messages=messages,
        model_call=model_call,
        parse_fn=_parse_json_response,
        validate_fn=_validate,
        temperatures=temps,
    )

    validation = result.get("validation") if isinstance(result.get("validation"), dict) else None
    out = {
        "input": result["input"],
        "output": result["output"],
        **({"validation": validation} if validation else {}),
    }
    if idea_id and plan_id:
        asyncio.create_task(save_ai_response(
            idea_id, plan_id, "format", task.get("task_id", ""),
            {"content": {"input": result["input"], "output": result["output"], "validation": validation or {}}, "reasoning": ""},
        ))
    return out


async def assess_quality(
    plan: Dict,
    on_thinking: Callable[[str], None],
    abort_event: Optional[Any],
    use_mock: bool = False,
    api_config: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Assess plan quality. Plan Agent LLM single-turn. Returns {score, comment}."""
    raise_if_aborted(abort_event)
    idea = plan.get("idea", "")
    tasks = plan.get("tasks") or []
    lines = []
    for t in tasks:
        tid = t.get("task_id", "")
        desc = (t.get("description") or "")[:80]
        deps = ",".join(t.get("dependencies") or [])
        has_io = "✓" if (t.get("input") and t.get("output")) else ""
        lines.append(f"- {tid}: {desc} | deps:[{deps}] {has_io}")
    tasks_summary = "\n".join(lines) if lines else "(no tasks)"
    ctx: Dict[str, Any] = {
        "type": "quality",
        "taskId": "_",
        "task": {},
        "qualityContext": {"idea": idea, "tasksSummary": tasks_summary},
    }
    try:
        messages, _phase = _build_messages_for_context(ctx)
        model_call = make_model_call(
            context=ctx, on_thinking=on_thinking, abort_event=abort_event,
            use_mock=use_mock, api_config=api_config,
        )

        def _validate(parsed: Any) -> tuple[bool, str]:
            if not isinstance(parsed, dict):
                return False, "Quality response must be a JSON object"
            if "score" not in parsed:
                return False, "Quality response missing score"
            return True, ""

        result, _raw = await generate_with_repair(
            base_messages=messages,
            model_call=model_call,
            parse_fn=_parse_json_response,
            validate_fn=_validate,
            temperatures=[TEMP_STRUCTURED] + [TEMP_RETRY] * PLAN_MAX_VALIDATION_RETRIES,
        )
        score = result.get("score")
        if isinstance(score, (int, float)):
            score = max(0, min(100, int(score)))
        else:
            score = 0
        comment = result.get("comment") or ""
        return {"score": score, "comment": str(comment)}
    except Exception:
        return {"score": 0, "comment": "Assessment skipped"}
