"""
Plan Agent 单轮 LLM 实现 - atomicity, decompose, format, quality.
Agent 实现放在 plan_agent/，单轮 LLM 放在 plan_agent/llm/。
"""

import asyncio
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import networkx as nx
import orjson
import json_repair

from db import save_ai_response
from shared.graph import build_dependency_graph, get_ancestor_path, get_parent_id
from shared.llm_client import chat_completion as real_chat_completion, merge_phase_config
from test.mock_stream import mock_chat_completion

PLAN_DIR = Path(__file__).resolve().parent.parent
MOCK_AI_DIR = PLAN_DIR.parent / "test" / "mock-ai"
MAX_CONCURRENT_CALLS = 10
MAX_VALIDATION_RETRIES = 2
RETRY_TEMPERATURE = 0.5
MAX_PLAN_AGENT_TURNS = 30

# Caches
_prompt_cache: Dict[str, str] = {}
_mock_cache: Dict[str, Dict] = {}
_call_semaphore: Optional[asyncio.Semaphore] = None


def _get_call_semaphore() -> asyncio.Semaphore:
    global _call_semaphore
    if _call_semaphore is None:
        _call_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CALLS)
    return _call_semaphore


def _get_prompt_cached(filename: str) -> str:
    if filename not in _prompt_cache:
        path = PLAN_DIR / "prompts" / filename
        _prompt_cache[filename] = path.read_text(encoding="utf-8").strip()
    return _prompt_cache[filename]


def _get_mock_cached(response_type: str) -> Dict:
    if response_type not in _mock_cache:
        path = MOCK_AI_DIR / f"{response_type}.json"
        try:
            _mock_cache[response_type] = orjson.loads(path.read_bytes())
        except (FileNotFoundError, orjson.JSONDecodeError):
            _mock_cache[response_type] = {}
    return _mock_cache[response_type]


async def _load_mock_response(response_type: str, task_id: str) -> Optional[Dict]:
    """Load mock from test/mock-ai/."""
    data = _get_mock_cached(response_type)
    entry = data.get(task_id) or data.get("_default")
    if not entry:
        return None
    content = entry.get("content")
    if isinstance(content, str):
        content_str = content
    else:
        content_str = orjson.dumps(content).decode("utf-8")
    return {"content": content_str, "reasoning": entry.get("reasoning", "")}


_OP_LABELS = {
    "atomicity": "Atomicity",
    "decompose": "Decompose",
    "format": "Format",
    "quality": "Quality",
}


def _build_user_message(response_type: str, task: Dict, context: Optional[Dict] = None) -> str:
    tid = task.get("task_id", "")
    desc = task.get("description", "")
    if response_type == "atomicity":
        parts = [f'Input: task_id "{tid}", description "{desc}"']
        ctx = context or {}
        if ctx.get("depth") is not None:
            parts.append(f'\nContext - depth: {ctx["depth"]}')
        if ctx.get("ancestor_path"):
            parts.append(f'\nContext - ancestor path: {ctx["ancestor_path"]}')
        if ctx.get("idea"):
            parts.append(f'\nContext - idea: {ctx["idea"]}')
        if ctx.get("siblings"):
            sib = ctx["siblings"]
            if isinstance(sib, list):
                sib_str = "; ".join(f'{t.get("task_id","")}: {t.get("description","")}' for t in sib if t.get("task_id"))
            else:
                sib_str = str(sib)
            if sib_str:
                parts.append(f'\nContext - sibling tasks: {sib_str}')
        parts.append('\nOutput:')
        return "".join(parts)
    if response_type == "decompose":
        parts = [f'**Input:** task_id "{tid}", description "{desc}"']
        ctx = context or {}
        if ctx.get("depth") is not None:
            parts.append(f'\n**Context - depth:** {ctx["depth"]}')
        if ctx.get("ancestor_path"):
            parts.append(f'\n**Context - ancestor path:** {ctx["ancestor_path"]}')
        if ctx.get("idea"):
            parts.append(f'\n**Context - idea:** {ctx["idea"]}')
        if ctx.get("siblings"):
            sib = ctx["siblings"]
            if isinstance(sib, list):
                sib_str = "; ".join(f'{t.get("task_id","")}: {t.get("description","")}' for t in sib if t.get("task_id"))
            else:
                sib_str = str(sib)
            if sib_str:
                parts.append(f'\n**Context - sibling tasks:** {sib_str}')
        parts.append('\n\n**Output:**')
        return "".join(parts)
    if response_type == "quality":
        ctx = context or {}
        idea = ctx.get("idea", "")
        tasks_summary = ctx.get("tasksSummary", "")
        return f'**Idea:** {idea}\n\n**Tasks:**\n{tasks_summary}\n\n**Output:**'
    if response_type == "format":
        return f'**Input task:** task_id "{tid}", description "{desc}"\n\n**Output:**'
    return f"Task: {tid} - {desc}"


async def _call_chat_completion(
    on_thinking: Callable[..., None],
    context: Dict,
    abort_event: Optional[Any],
    stream: bool = True,
    use_mock: bool = False,
    api_config: Optional[Dict] = None,
    temperature: Optional[float] = None,
    plan_id: Optional[str] = None,
) -> str:
    response_type = context["type"]
    task_id = context["taskId"]
    task = context.get("task", {})

    def stream_chunk(chunk: str) -> None:
        if on_thinking and chunk:
            op_label = _OP_LABELS.get(response_type, response_type.capitalize())
            on_thinking(chunk, task_id=task_id, operation=op_label)

    if use_mock:
        mock = await _load_mock_response(response_type, task_id)
        if not mock:
            raise ValueError(f"No mock data for {response_type}/{task_id}")
        effective_on_thinking = stream_chunk if (stream and on_thinking) else None
        async with _get_call_semaphore():
            return await mock_chat_completion(
                mock["content"],
                mock["reasoning"],
                effective_on_thinking,
                abort_event=abort_event,
                stream=stream,
            )

    # Real LLM
    prompt_file = {
        "atomicity": "atomicity-prompt.txt",
        "decompose": "decompose-prompt.txt",
        "format": "format-prompt.txt",
        "quality": "quality-assess-prompt.txt",
    }.get(response_type, "atomicity-prompt.txt")
    system_prompt = _get_prompt_cached(prompt_file)
    msg_ctx = (
        context.get("decomposeContext") if response_type == "decompose"
        else context.get("qualityContext") if response_type == "quality"
        else context.get("atomicityContext") if response_type == "atomicity"
        else None
    )
    user_message = _build_user_message(response_type, context.get("task", {}), msg_ctx)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    if response_type == "atomicity":
        phase = "atomicity"
    elif response_type == "quality":
        phase = "quality"
    elif response_type == "decompose":
        phase = "decompose"
    else:
        phase = "format"
    cfg = merge_phase_config(api_config, phase)
    effective_on_chunk = stream_chunk if (stream and on_thinking) else None
    response_format = {"type": "json_object"} if response_type in ("atomicity", "quality") else None
    async with _get_call_semaphore():
        return await real_chat_completion(
            messages,
            cfg,
            on_chunk=effective_on_chunk,
            abort_event=abort_event,
            stream=stream,
            temperature=temperature,
            response_format=response_format,
        )


def _parse_json_response(text: str) -> Any:
    """Parse JSON from AI response using json_repair for malformed output."""
    cleaned = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if m:
        cleaned = m.group(1).strip()
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
    plan_id: Optional[str] = None,
) -> Dict:
    """Check if task is atomic. Plan Agent LLM single-turn."""
    raise_if_aborted(abort_event)
    ctx: Dict[str, Any] = {"type": "atomicity", "taskId": task["task_id"], "task": task}
    if atomicity_context:
        ctx["atomicityContext"] = atomicity_context
    last_err: Optional[Exception] = None
    for attempt in range(MAX_VALIDATION_RETRIES + 1):
        raise_if_aborted(abort_event)
        try:
            content = await _call_chat_completion(
                on_thinking,
                ctx,
                abort_event,
                stream=False,
                use_mock=use_mock,
                api_config=api_config,
                temperature=0.0 if attempt == 0 else RETRY_TEMPERATURE,
                plan_id=plan_id,
            )
            result = _parse_json_response(content)
            if not _validate_atomicity_response(result):
                raise ValueError("Atomicity response invalid: missing or invalid atomic field")
            out = {"atomic": bool(result.get("atomic"))}
            if plan_id:
                asyncio.create_task(save_ai_response(
                    plan_id, "atomicity", task["task_id"],
                    {"content": {"atomic": out["atomic"]}, "reasoning": ""},
                ))
            return out
        except Exception as e:
            last_err = e
            if attempt >= MAX_VALIDATION_RETRIES:
                raise
    raise last_err or ValueError("Atomicity check failed")


async def decompose_task(
    parent_task: Dict,
    on_thinking: Callable[[str], None],
    abort_event: Optional[Any],
    all_tasks: List[Dict],
    idea: Optional[str] = None,
    depth: int = 0,
    use_mock: bool = False,
    api_config: Optional[Dict] = None,
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
    last_err: Optional[Exception] = None
    for attempt in range(MAX_VALIDATION_RETRIES + 1):
        raise_if_aborted(abort_event)
        try:
            content = await _call_chat_completion(
                on_thinking,
                ctx,
                abort_event,
                stream=True,
                use_mock=use_mock,
                api_config=api_config,
                temperature=RETRY_TEMPERATURE if attempt > 0 else None,
                plan_id=plan_id,
            )
            result = _parse_json_response(content)
            valid, err_msg = _validate_decompose_response(result, pid)
            if not valid:
                raise ValueError(f"Decompose validation failed: {err_msg}")
            tasks = result.get("tasks") or []
            out = [
                t
                for t in tasks
                if t.get("task_id") and t.get("description") and isinstance(t.get("dependencies"), list)
            ]
            if plan_id:
                asyncio.create_task(save_ai_response(
                    plan_id, "decompose", pid,
                    {"content": {"tasks": tasks}, "reasoning": ""},
                ))
            return out
        except Exception as e:
            last_err = e
            if attempt >= MAX_VALIDATION_RETRIES:
                raise
    raise last_err or ValueError("Decompose failed")


async def format_task(
    task: Dict,
    on_thinking: Callable[[str], None],
    abort_event: Optional[Any],
    use_mock: bool = False,
    api_config: Optional[Dict] = None,
    plan_id: Optional[str] = None,
) -> Optional[Dict]:
    """Generate input/output spec for atomic task. Plan Agent LLM single-turn."""
    raise_if_aborted(abort_event)
    content = await _call_chat_completion(
        on_thinking,
        {"type": "format", "taskId": task.get("task_id", ""), "task": task},
        abort_event,
        stream=True,
        use_mock=use_mock,
        api_config=api_config,
        plan_id=plan_id,
    )
    result = _parse_json_response(content)
    if not result.get("input") or not result.get("output"):
        return None
    validation = result.get("validation") if isinstance(result.get("validation"), dict) else None
    out = {
        "input": result["input"],
        "output": result["output"],
        **({"validation": validation} if validation else {}),
    }
    if plan_id:
        asyncio.create_task(save_ai_response(
            plan_id, "format", task.get("task_id", ""),
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
    if use_mock:
        return {"score": 85, "comment": "Mock assessment"}
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
        content = await _call_chat_completion(
            on_thinking,
            ctx,
            abort_event,
            stream=False,
            use_mock=use_mock,
            api_config=api_config,
        )
        result = _parse_json_response(content)
        score = result.get("score")
        if isinstance(score, (int, float)):
            score = max(0, min(100, int(score)))
        else:
            score = 0
        comment = result.get("comment") or ""
        return {"score": score, "comment": str(comment)}
    except Exception:
        return {"score": 0, "comment": "Assessment skipped"}
