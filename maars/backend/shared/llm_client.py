"""
LLM client for Plan Agent and Task Agent. Uses Google GenAI SDK (Gemini API only).
"""

import asyncio
import json
from typing import Any, Callable, List, Optional, Union

from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-2.5-flash"


def merge_phase_config(api_config: dict, phase: str) -> dict:
    """
    Merge global api_config with phase-specific overrides.
    phase: atomicity | decompose | format | execute | validate
    Returns dict with apiKey, model (camelCase for compatibility).
    """
    cfg = dict(api_config or {})
    phases = cfg.get("phases") or {}
    phase_cfg = phases.get(phase) or {}
    if isinstance(phase_cfg, dict):
        base = {
            "baseUrl": cfg.get("baseUrl") or cfg.get("base_url"),
            "apiKey": cfg.get("apiKey") or cfg.get("api_key"),
            "model": cfg.get("model"),
        }
        for k, v in phase_cfg.items():
            key = k if k in ("baseUrl", "apiKey", "model") else {"base_url": "baseUrl", "api_key": "apiKey"}.get(k, k)
            if v is not None and v != "":
                base[key] = v
        if not base.get("model"):
            base["model"] = DEFAULT_MODEL
        return base
    return cfg


def _tools_to_gemini(tools: List[dict]) -> List[Any]:
    """Convert OpenAI-style tools format to google-genai types.Tool."""
    declarations = []
    for t in tools or []:
        fn = t.get("function") if isinstance(t, dict) else getattr(t, "function", None)
        if not fn:
            continue
        fn = fn if isinstance(fn, dict) else {}
        name = fn.get("name") or ""
        desc = fn.get("description") or ""
        params = fn.get("parameters") or {"type": "object", "properties": {}}
        declarations.append(
            types.FunctionDeclaration(
                name=name,
                description=desc,
                parameters_json_schema=params,
            )
        )
    if not declarations:
        return []
    return [types.Tool(function_declarations=declarations)]


def _messages_to_gemini_contents(messages: list[dict]) -> tuple[List[Any], Optional[str]]:
    """
    Convert messages to Google contents. Returns (contents, system_instruction).
    Supports gemini_model_content in assistant messages for native thought_signature.
    """
    contents: List[Any] = []
    system_instruction: Optional[str] = None
    id_to_name: dict = {}

    for m in messages:
        role = (m.get("role") or "").lower()

        if role == "system":
            system_instruction = m.get("content") or ""
            continue

        if role == "user":
            text = m.get("content") or ""
            if text:
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))
            continue

        if role == "assistant":
            raw = m.get("gemini_model_content")
            if raw is not None:
                contents.append(raw)
                continue
            text = m.get("content") or ""
            tool_calls = m.get("tool_calls") or []
            for tc in tool_calls:
                fn = tc.get("function") or {}
                tid = tc.get("id") or ""
                if tid:
                    id_to_name[tid] = fn.get("name") or ""
            if tool_calls:
                parts = []
                if text:
                    parts.append(types.Part.from_text(text=text))
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    name = fn.get("name") or ""
                    args = fn.get("arguments") or "{}"
                    try:
                        args_dict = json.loads(args) if isinstance(args, str) else (args or {})
                    except json.JSONDecodeError:
                        args_dict = {}
                    part = types.Part.from_function_call(name=name, args=args_dict)
                    try:
                        if tc.get("thought_signature") is not None:
                            part.thought_signature = tc["thought_signature"]
                    except Exception:
                        pass
                    parts.append(part)
                if parts:
                    contents.append(types.Content(role="model", parts=parts))
            elif text:
                contents.append(types.Content(role="model", parts=[types.Part.from_text(text=text)]))
            continue

        if role == "tool":
            tool_call_id = m.get("tool_call_id") or ""
            content = m.get("content") or ""
            name = id_to_name.get(tool_call_id) or "tool"
            contents.append(
                types.Content(
                    role="tool",
                    parts=[types.Part.from_function_response(name=name, response={"result": content})],
                )
            )
            continue

    return contents, system_instruction


async def chat_completion(
    messages: list[dict],
    api_config: dict,
    on_chunk: Optional[Callable[[str], None]] = None,
    abort_event: Optional[Any] = None,
    stream: bool = True,
    temperature: Optional[float] = None,
    response_format: Optional[dict] = None,
    tools: Optional[List[dict]] = None,
) -> Union[str, dict]:
    """
    Call Gemini chat completions API.
    When tools provided: returns dict with content, tool_calls, finish_reason, gemini_model_content.
    """
    cfg = dict(api_config or {})
    model = cfg.get("model") or DEFAULT_MODEL
    temp = temperature if temperature is not None else cfg.get("temperature")
    api_key = cfg.get("apiKey") or cfg.get("api_key") or ""

    client = genai.Client(api_key=api_key)
    contents, system_instruction = _messages_to_gemini_contents(messages)

    config_kw: dict = {}
    if system_instruction:
        config_kw["system_instruction"] = system_instruction
    if temp is not None:
        config_kw["temperature"] = temp
    if response_format and response_format.get("type") == "json_object":
        config_kw["response_mime_type"] = "application/json"

    if tools:
        config_kw["tools"] = _tools_to_gemini(tools)
        config_kw.pop("response_mime_type", None)
        stream = False

    config = types.GenerateContentConfig(**config_kw) if config_kw else None

    try:
        aclient = client.aio
        try:
            if abort_event and abort_event.is_set():
                raise asyncio.CancelledError("Aborted")

            if stream and not tools:
                full_content = []
                async for chunk in await aclient.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=config,
                ):
                    if abort_event and abort_event.is_set():
                        raise asyncio.CancelledError("Aborted")
                    text = chunk.text or ""
                    if text and on_chunk:
                        r = on_chunk(text)
                        if asyncio.iscoroutine(r):
                            await r
                    full_content.append(text)
                return "".join(full_content)

            resp = await aclient.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        finally:
            await aclient.aclose()
    except Exception as e:
        raise RuntimeError(f"Gemini API error: {e}") from e

    if abort_event and abort_event.is_set():
        raise asyncio.CancelledError("Aborted")

    function_calls = getattr(resp, "function_calls", None) or []
    if function_calls and resp.candidates:
        model_content = resp.candidates[0].content
        tool_calls = []
        for i, fc in enumerate(function_calls):
            name = getattr(fc, "name", None) or ""
            fn_call = getattr(fc, "function_call", None)
            args = getattr(fn_call, "args", None) if fn_call else getattr(fc, "args", None)
            if args is None and fn_call is not None:
                args = fn_call
            if hasattr(args, "args"):
                args = getattr(args, "args", args)
            args_str = json.dumps(args) if isinstance(args, dict) else (str(args) if args else "{}")
            tool_calls.append({
                "id": f"gc_{i}",
                "type": "function",
                "function": {"name": name, "arguments": args_str},
            })

        return {
            "content": resp.text or "",
            "tool_calls": tool_calls,
            "finish_reason": "tool_calls",
            "gemini_model_content": model_content,
        }

    return resp.text or ""
