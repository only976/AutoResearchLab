"""
Task Agent 单轮 LLM 实现 - 任务执行。
Agent 实现放在 task_agent/，单轮 LLM 放在 task_agent/llm/。
Generates output from task description and input artifacts.
Supports mock mode (useMock=True): returns simulated output without LLM calls.
Supports streaming via on_thinking callback for real-time output display.
"""

import asyncio
import re
from typing import Any, Callable, Dict, Optional

import orjson
import json_repair

from shared.llm_client import chat_completion, merge_phase_config
from shared.utils import chunk_string

# Mock 模式下 chunk 间延迟（秒）
_MOCK_CHUNK_DELAY = 0.03


async def _mock_execute(output_format: str, task_id: str, on_thinking: Optional[Callable] = None) -> Any:
    """Return simulated output for mock mode. No LLM call."""
    if _is_json_format(output_format):
        result = {"_mock": True, "task_id": task_id, "note": "Simulated output (Mock AI mode)"}
        if on_thinking:
            for chunk in chunk_string(orjson.dumps(result, option=orjson.OPT_INDENT_2).decode("utf-8"), 20):
                r = on_thinking(chunk, task_id=task_id, operation="Execute")
                if asyncio.iscoroutine(r):
                    await r
                await asyncio.sleep(_MOCK_CHUNK_DELAY)
        return result
    text = f"# Mock Output\n\nSimulated content for task {task_id}.\n\n(Mock AI mode)"
    if on_thinking:
        for chunk in chunk_string(text, 20):
            r = on_thinking(chunk, task_id=task_id, operation="Execute")
            if asyncio.iscoroutine(r):
                await r
            await asyncio.sleep(_MOCK_CHUNK_DELAY)
    return text


def _is_json_format(output_format: str) -> bool:
    if not output_format:
        return False
    fmt = output_format.strip().upper()
    return fmt.startswith("JSON") or "JSON" in fmt


def _build_task_agent_messages(
    task_id: str,
    description: str,
    input_spec: Dict[str, Any],
    output_spec: Dict[str, Any],
    resolved_inputs: Dict[str, Any],
) -> tuple[list[dict], str]:
    """Build system + user messages for single-turn Task Agent."""
    output_format = output_spec.get("format") or ""
    output_desc = output_spec.get("description") or ""
    input_desc = input_spec.get("description") or ""

    system_prompt = """You are a Task Agent. Your job is to complete a single atomic task and produce output in the exact format specified.

Rules:
1. Use only the provided input artifacts and task description.
2. Output must strictly conform to the specified format.
3. For JSON: output valid JSON only, no extra text or markdown fences.
4. For Markdown: output the document content directly."""

    inputs_str = "No input artifacts."
    if resolved_inputs:
        try:
            inputs_str = orjson.dumps(resolved_inputs, option=orjson.OPT_INDENT_2).decode("utf-8")
        except (TypeError, ValueError):
            inputs_str = str(resolved_inputs)

    user_prompt = f"""**Task ID:** {task_id}
**Description:** {description}

**Input description:** {input_desc}
**Input artifacts:**
```json
{inputs_str}
```

**Output description:** {output_desc}
**Output format:** {output_format}

Produce the output now. Output ONLY the result, no explanation."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return messages, output_format


def _parse_task_agent_output(content: str, use_json_mode: bool) -> Any:
    """Parse Task Agent output (content) to final result."""
    content = (content or "").strip()
    if not content:
        raise ValueError("LLM returned empty response")
    if use_json_mode:
        cleaned = content
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
        if m:
            cleaned = m.group(1).strip()
        try:
            return json_repair.loads(cleaned)
        except Exception as e:
            raise ValueError(f"Failed to parse JSON from LLM response: {e}") from e
    return content


def _get_task_agent_params(api_config: Dict[str, Any]) -> tuple[int, float]:
    """Return (max_turns, temperature) from modeConfig or defaults. Used for single-turn temperature."""
    mode_cfg = api_config.get("modeConfig") or {}
    agent_cfg = mode_cfg.get("agent") or {}
    llm_cfg = mode_cfg.get("llm") or {}
    temperature = (
        agent_cfg.get("taskLlmTemperature")
        or llm_cfg.get("taskLlmTemperature")
        or 0.3
    )
    return 1, float(temperature)


async def execute_task(
    task_id: str,
    description: str,
    input_spec: Dict[str, Any],
    output_spec: Dict[str, Any],
    resolved_inputs: Dict[str, Any],
    api_config: Optional[Dict[str, Any]] = None,
    abort_event: Optional[Any] = None,
    on_thinking: Optional[Callable[[str, Optional[str], Optional[str]], None]] = None,
    plan_id: Optional[str] = None,
) -> Any:
    """
    Execute task via single-turn LLM. Returns parsed output (dict for JSON, str for Markdown).
    When useMock=True in api_config, returns simulated output without LLM call.
    When taskAgentMode=True, caller (runner) should use task_agent.agent.run_task_agent instead.
    """
    raw_cfg = api_config or {}
    if raw_cfg.get("useMock"):
        output_format = (output_spec or {}).get("format") or ""
        return await _mock_execute(output_format, task_id, on_thinking)

    cfg = merge_phase_config(raw_cfg, "execute")
    _, temperature = _get_task_agent_params(raw_cfg)
    messages, output_format = _build_task_agent_messages(
        task_id, description, input_spec, output_spec, resolved_inputs
    )
    use_json_mode = _is_json_format(output_format)
    response_format = {"type": "json_object"} if use_json_mode else None
    stream = on_thinking is not None

    def _on_chunk(chunk: str):
        if on_thinking and chunk:
            return on_thinking(chunk, task_id=task_id, operation="Execute")

    raw = await chat_completion(
        messages,
        cfg,
        on_chunk=_on_chunk if stream else None,
        abort_event=abort_event,
        stream=stream,
        temperature=temperature,
        response_format=response_format,
    )
    content = raw if isinstance(raw, str) else (raw.get("content") or "")
    return _parse_task_agent_output(content, use_json_mode)
