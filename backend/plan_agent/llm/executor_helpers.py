"""Shared helper functions for plan-agent LLM executor."""

import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from shared.constants import PLAN_MAX_CONCURRENT_CALLS
from shared.llm_client import chat_completion as real_chat_completion, merge_phase_config
from shared.mock_utils import get_mock_cached, load_mock_entry
from test.mock_stream import mock_chat_completion

PLAN_DIR = Path(__file__).resolve().parent.parent
MOCK_AI_DIR = PLAN_DIR.parent / "test" / "mock-ai"

_prompt_cache: Dict[str, str] = {}
_call_semaphore: Optional[asyncio.Semaphore] = None


def _get_call_semaphore() -> asyncio.Semaphore:
    global _call_semaphore
    if _call_semaphore is None:
        _call_semaphore = asyncio.Semaphore(PLAN_MAX_CONCURRENT_CALLS)
    return _call_semaphore


def _get_prompt_cached(filename: str) -> str:
    if filename not in _prompt_cache:
        path = PLAN_DIR / "prompts" / filename
        _prompt_cache[filename] = path.read_text(encoding="utf-8").strip()
    return _prompt_cache[filename]


async def _load_mock_response(response_type: str, task_id: str) -> Optional[Dict]:
    """Load mock from test/mock-ai/. Fallback to _default reasoning when empty."""
    mock = load_mock_entry(MOCK_AI_DIR, response_type, task_id)
    if not mock:
        return None
    # Plan agent: fallback to _default reasoning when entry reasoning is empty
    if not (mock.get("reasoning") or "").strip():
        data = get_mock_cached(MOCK_AI_DIR, response_type)
        default_entry = data.get("_default") or {}
        mock["reasoning"] = default_entry.get("reasoning", "")
    return mock


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


def _build_messages_for_context(context: Dict[str, Any]) -> tuple[list[dict], str]:
    response_type = context["type"]
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
    return messages, phase


def make_model_call(
    *,
    context: Dict[str, Any],
    on_thinking: Callable[..., None],
    abort_event: Optional[Any],
    use_mock: bool,
    api_config: Optional[Dict],
) -> Callable[[list[dict], float], Awaitable[str]]:
    """Create a model_call function compatible with generate_with_repair.

    Mock mode: ignores the messages arg, loads mock data via _call_chat_completion.
    Real mode: calls _call_real_chat_completion with the provided messages.
    """
    response_type = context["type"]
    task_id = context["taskId"]
    op_label = _OP_LABELS.get(response_type, response_type.capitalize())

    if use_mock:
        async def _mock_call(messages: list[dict], temperature: float) -> str:
            return await _call_chat_completion(
                on_thinking, context, abort_event,
                stream=True, use_mock=True, api_config=api_config,
                temperature=temperature,
            )
        return _mock_call

    phase = {
        "atomicity": "atomicity",
        "decompose": "decompose",
        "quality": "quality",
    }.get(response_type, "format")

    async def _real_call(messages: list[dict], temperature: float) -> str:
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
    return _real_call


async def _call_real_chat_completion(
    *,
    messages: list[dict],
    phase: str,
    on_thinking: Callable[..., None],
    task_id: str,
    op_label: str,
    abort_event: Optional[Any],
    api_config: Optional[Dict],
    temperature: float,
) -> str:
    cfg = merge_phase_config(api_config, phase)

    def stream_chunk(chunk: str):
        if on_thinking and chunk:
            return on_thinking(chunk, task_id=task_id, operation=op_label)

    async with _get_call_semaphore():
        content = await real_chat_completion(
            messages,
            cfg,
            on_chunk=stream_chunk if on_thinking else None,
            abort_event=abort_event,
            stream=bool(on_thinking),
            temperature=temperature,
        )
    return content or ""


async def _call_chat_completion(
    on_thinking: Callable[..., None],
    context: Dict,
    abort_event: Optional[Any],
    stream: bool = True,
    use_mock: bool = False,
    api_config: Optional[Dict] = None,
    temperature: Optional[float] = None,
) -> str:
    response_type = context["type"]
    task_id = context["taskId"]
    op_label = _OP_LABELS.get(response_type, response_type.capitalize())

    def stream_chunk(chunk: str):
        if on_thinking and chunk:
            return on_thinking(chunk, task_id=task_id, operation=op_label)

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

    messages, phase = _build_messages_for_context(context)
    async with _get_call_semaphore():
        cfg = merge_phase_config(api_config, phase)
        content = await real_chat_completion(
            messages,
            cfg,
            on_chunk=stream_chunk if (stream and on_thinking) else None,
            abort_event=abort_event,
            stream=stream,
            temperature=temperature,
        )
    return content or ""
