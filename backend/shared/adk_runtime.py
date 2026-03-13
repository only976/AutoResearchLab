"""
Shared Google ADK runtime utilities.
Centralizes runner lifecycle, event loop, abort handling, and finish payload parsing.
"""

import asyncio
import json
import time
import uuid
from typing import Any, Callable, Dict, Optional

import orjson
from google.adk import Agent, Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from loguru import logger

from shared.constants import ADK_IDLE_TIMEOUT_SECONDS, ADK_TOOL_WAIT_TIMEOUT_SECONDS

ToolCallHook = Callable[[str, Dict[str, Any], int], Any]
ToolResponseHook = Callable[[str, Any, int], Any]
TextHook = Callable[[str, int], Any]


async def _maybe_await(value: Any) -> None:
    if asyncio.iscoroutine(value):
        await value


async def _invoke_hook(hook: Any, *args: Any) -> None:
    if hook is None:
        return
    try:
        await _maybe_await(hook(*args))
    except TypeError:
        # Backward-compat for callbacks that don't accept token usage arg.
        if len(args) >= 1:
            await _maybe_await(hook(*args[:-1]))


def _to_dict(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            d = dict(vars(value))
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return {}


def _extract_token_usage(event: Any) -> Dict[str, int]:
    """Best-effort token usage extraction across ADK/Gemini response shapes."""
    candidates: list[dict] = []

    e_dict = _to_dict(event)
    if e_dict:
        candidates.append(e_dict)

    for attr in ("usage_metadata", "usageMetadata", "usage"):
        val = getattr(event, attr, None)
        d = _to_dict(val)
        if d:
            candidates.append(d)

    content = getattr(event, "content", None)
    c_dict = _to_dict(content)
    if c_dict:
        candidates.append(c_dict)

    for container in candidates:
        for key in ("usage_metadata", "usageMetadata", "usage"):
            nested = container.get(key) if isinstance(container, dict) else None
            d = _to_dict(nested)
            if d:
                candidates.append(d)

    keys = {
        "input": ("prompt_token_count", "input_tokens", "promptTokens", "promptTokenCount", "inputTokenCount"),
        "output": ("candidates_token_count", "output_tokens", "completion_tokens", "outputTokens", "candidatesTokenCount", "outputTokenCount"),
        "total": ("total_token_count", "total_tokens", "totalTokens", "totalTokenCount"),
    }

    result: Dict[str, int] = {}
    for bucket, names in keys.items():
        for c in candidates:
            if not isinstance(c, dict):
                continue
            for name in names:
                raw = c.get(name)
                if raw is None:
                    continue
                try:
                    val = int(raw)
                except Exception:
                    continue
                if val >= 0:
                    result[bucket] = max(result.get(bucket, 0), val)
    if "total" not in result:
        inp = result.get("input")
        out = result.get("output")
        if inp is not None or out is not None:
            result["total"] = int(inp or 0) + int(out or 0)
    return result


def build_tool_args_preview(args: Dict[str, Any], max_len: int = 200) -> str:
    preview = json.dumps(args or {}, ensure_ascii=False)
    if len(preview) > max_len:
        return preview[:max_len] + "..."
    return preview


def parse_function_response_payload(response: Any) -> Dict[str, Any]:
    """
    Parse function response payload into dict.
    ADK response shape can vary across tool implementations.
    """
    if not response:
        return {}
    raw = response.get("result", response) if isinstance(response, dict) else response
    if isinstance(raw, dict):
        return raw
    try:
        return orjson.loads(str(raw))
    except Exception:
        return {}


async def run_adk_agent_loop(
    *,
    app_name: str,
    agent_name: str,
    model: str,
    instruction: str,
    tools: list[Any],
    user_message: str,
    max_turns: int,
    abort_event: Optional[Any] = None,
    abort_message: str = "Agent aborted",
    on_tool_call: Optional[ToolCallHook] = None,
    on_tool_response: Optional[ToolResponseHook] = None,
    on_text: Optional[TextHook] = None,
    user_id: str = "maars_user",
    session_id: Optional[str] = None,
    idle_timeout_seconds: Optional[int] = None,
) -> int:
    """
    Run one ADK agent session and invoke hooks for tool calls/responses and model text.
    Returns observed turn count.
    """
    agent = Agent(
        model=model,
        name=agent_name,
        instruction=instruction,
        tools=tools,
    )
    runner = Runner(
        agent=agent,
        app_name=app_name,
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )
    new_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_message)],
    )
    effective_session_id = session_id or str(uuid.uuid4())
    turn_count = 0
    event_count = 0
    idle_timeout = max(5, int(idle_timeout_seconds or ADK_IDLE_TIMEOUT_SECONDS))
    tool_wait_timeout = max(idle_timeout, int(ADK_TOOL_WAIT_TIMEOUT_SECONDS))
    started_at = time.monotonic()
    waiting_for_tool_response = False
    pending_tool_name = ""
    token_totals: Dict[str, int] = {"input": 0, "output": 0, "total": 0}

    async def _run() -> None:
        nonlocal turn_count, event_count, waiting_for_tool_response, pending_tool_name
        try:
            event_iter = runner.run_async(
                user_id=user_id,
                session_id=effective_session_id,
                new_message=new_message,
            ).__aiter__()

            while True:
                try:
                    use_extended_wait = waiting_for_tool_response or event_count == 0
                    wait_timeout = tool_wait_timeout if use_extended_wait else idle_timeout
                    event = await asyncio.wait_for(anext(event_iter), timeout=wait_timeout)
                except StopAsyncIteration:
                    logger.info(
                        "ADK loop finished agent={} turns={} events={} elapsed_ms={}",
                        agent_name,
                        turn_count,
                        event_count,
                        int((time.monotonic() - started_at) * 1000),
                    )
                    break
                except asyncio.TimeoutError as e:
                    logger.warning(
                        "ADK loop idle timeout agent={} turns={} events={} idle_timeout_s={} waiting_for_tool_response={} pending_tool={} elapsed_ms={}",
                        agent_name,
                        turn_count,
                        event_count,
                        wait_timeout,
                        waiting_for_tool_response,
                        pending_tool_name,
                        int((time.monotonic() - started_at) * 1000),
                    )
                    if waiting_for_tool_response and pending_tool_name:
                        raise TimeoutError(
                            f"{agent_name} timed out after {wait_timeout} seconds waiting for tool response: {pending_tool_name}"
                        ) from e
                    raise TimeoutError(
                        f"{agent_name} idle for more than {wait_timeout} seconds while waiting for the next ADK event"
                    ) from e

                if abort_event and abort_event.is_set():
                    raise asyncio.CancelledError(abort_message)

                event_count += 1
                turn_count += 1
                usage = _extract_token_usage(event)
                token_delta = {"input": 0, "output": 0, "total": 0}
                for key in ("input", "output", "total"):
                    cur = int(usage.get(key, token_totals.get(key, 0)) or 0)
                    prev = int(token_totals.get(key, 0) or 0)
                    if cur >= prev:
                        token_delta[key] = cur - prev
                        token_totals[key] = cur
                    else:
                        token_delta[key] = 0
                token_usage = {
                    "input": int(token_totals.get("input", 0)),
                    "output": int(token_totals.get("output", 0)),
                    "total": int(token_totals.get("total", 0)),
                    "deltaInput": int(token_delta.get("input", 0)),
                    "deltaOutput": int(token_delta.get("output", 0)),
                    "deltaTotal": int(token_delta.get("total", 0)),
                }
                if turn_count > max_turns:
                    logger.warning(
                        "ADK loop reached max turns agent={} max_turns={} events={} elapsed_ms={}",
                        agent_name,
                        max_turns,
                        event_count,
                        int((time.monotonic() - started_at) * 1000),
                    )
                    break

                if not event.content or not event.content.parts:
                    continue

                get_calls = getattr(event, "get_function_calls", None)
                get_responses = getattr(event, "get_function_responses", None)
                calls = get_calls() if callable(get_calls) else []
                responses = get_responses() if callable(get_responses) else []

                if calls:
                    waiting_for_tool_response = True
                    for call in calls:
                        name = getattr(call, "name", None) or ""
                        pending_tool_name = name or pending_tool_name
                        args = getattr(call, "args", None) or {}
                        logger.info(
                            "ADK tool call agent={} turn={} tool={} args_preview={}",
                            agent_name,
                            turn_count,
                            name,
                            build_tool_args_preview(args),
                        )
                        if on_tool_call:
                            await _invoke_hook(on_tool_call, name, args, turn_count, token_usage)
                    continue

                if responses:
                    waiting_for_tool_response = False
                    pending_tool_name = ""
                    for response in responses:
                        name = getattr(response, "name", None) or ""
                        payload = getattr(response, "response", None)
                        payload_preview = str(payload)
                        if len(payload_preview) > 220:
                            payload_preview = payload_preview[:220] + "..."
                        logger.info(
                            "ADK tool response agent={} turn={} tool={} payload_preview={}",
                            agent_name,
                            turn_count,
                            name,
                            payload_preview,
                        )
                        if on_tool_response:
                            await _invoke_hook(on_tool_response, name, payload, turn_count, token_usage)
                    continue

                if on_text:
                    waiting_for_tool_response = False
                    pending_tool_name = ""
                    for part in event.content.parts:
                        text = getattr(part, "text", None) or ""
                        if text:
                            preview = text if len(text) <= 220 else text[:220] + "..."
                            logger.info(
                                "ADK text agent={} turn={} text_preview={}",
                                agent_name,
                                turn_count,
                                preview,
                            )
                            await _invoke_hook(on_text, text, turn_count, token_usage)
        finally:
            try:
                await runner.close()
            except Exception as e:
                logger.debug("Runner close: %s", e)

    run_task = asyncio.create_task(_run())
    if abort_event:
        while not run_task.done():
            await asyncio.sleep(0.3)
            if abort_event.is_set():
                run_task.cancel()
                try:
                    await run_task
                except asyncio.CancelledError:
                    pass
                raise asyncio.CancelledError(abort_message)
        await run_task
    else:
        await run_task

    return turn_count
