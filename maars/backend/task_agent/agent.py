"""
Task Agent - ReAct-style agent loop (taskAgentMode=True).
Uses ReadArtifact, ReadFile, WriteFile, Finish, ListSkills, etc. via TOOLS.
Agent 实现放在 task_agent/，单轮 LLM 放在 task_agent/llm/。
"""

import asyncio
import re
from typing import Any, Callable, Dict, Optional

import orjson
import json_repair

from db import ensure_sandbox_dir
from shared.llm_client import chat_completion, merge_phase_config

from .agent_tools import TOOLS, execute_tool

MAX_AGENT_TURNS = 15


def _get_task_agent_params(api_config: Dict[str, Any]) -> tuple[int, float]:
    """Return (max_turns, temperature) from modeConfig or defaults."""
    mode_cfg = api_config.get("modeConfig") or {}
    agent_cfg = mode_cfg.get("agent") or {}
    llm_cfg = mode_cfg.get("llm") or {}
    max_turns = agent_cfg.get("taskAgentMaxTurns") or MAX_AGENT_TURNS
    max_turns = int(max_turns)
    temperature = (
        agent_cfg.get("taskLlmTemperature")
        or llm_cfg.get("taskLlmTemperature")
        or 0.3
    )
    return max_turns, float(temperature)


def _is_json_format(output_format: str) -> bool:
    if not output_format:
        return False
    fmt = output_format.strip().upper()
    return fmt.startswith("JSON") or "JSON" in fmt


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


def _build_task_agent_messages(
    task_id: str,
    description: str,
    input_spec: Dict[str, Any],
    output_spec: Dict[str, Any],
    resolved_inputs: Dict[str, Any],
    validation_spec: Optional[Dict[str, Any]] = None,
) -> tuple[list[dict], str]:
    """Build system + user messages for Task Agent mode."""
    output_format = output_spec.get("format") or ""
    output_desc = output_spec.get("description") or ""
    input_desc = input_spec.get("description") or ""

    validation_rule = ""
    if validation_spec and (validation_spec.get("criteria") or validation_spec.get("optionalChecks")):
        validation_rule = """
5. **Validation (required when task has validation spec)**: Before calling Finish, you MUST validate your output. Load the task-output-validator skill, write output to sandbox (e.g. sandbox/output.json or sandbox/result.md), run its validate script with the validation criteria, fix any failures, then call Finish only when validation passes."""

    system_prompt = f"""You are a Task Agent. Your job is to complete a single atomic task and produce output in the exact format specified.

Rules:
1. Use only the provided input artifacts and task description.
2. Output must strictly conform to the specified format.
3. For JSON: output valid JSON only, no extra text or markdown fences.
4. For Markdown: output the document content directly.{validation_rule}

You have tools: ReadArtifact (read dependency task output), ReadFile (read files; use 'sandbox/X' for this task's sandbox), WriteFile (write to sandbox only), ListSkills, LoadSkill, ReadSkillFile (read skill's scripts/references), RunSkillScript (execute skill scripts, use {{sandbox}}/file for sandbox paths), WebSearch (search the web for research—use for benchmarks, docs, current data), WebFetch (fetch URL content for citations), Finish (submit final output).
Use ListSkills to discover skills, LoadSkill when relevant. ReadSkillFile and RunSkillScript let you use skill capabilities (e.g. docx validate, pptx convert). When your output satisfies the output spec, you MUST call Finish with the result—do not output inline. For JSON format pass a valid JSON string; for Markdown pass the content string. All file I/O is scoped to the plan dir and this task's sandbox."""

    inputs_str = "No input artifacts."
    if resolved_inputs:
        try:
            inputs_str = orjson.dumps(resolved_inputs, option=orjson.OPT_INDENT_2).decode("utf-8")
        except (TypeError, ValueError):
            inputs_str = str(resolved_inputs)

    validation_block = ""
    if validation_spec and (validation_spec.get("criteria") or validation_spec.get("optionalChecks")):
        criteria = validation_spec.get("criteria") or []
        optional = validation_spec.get("optionalChecks") or []
        criteria_text = "\n".join(f"- {c}" for c in criteria) if criteria else ""
        optional_text = "\n".join(f"- [optional] {c}" for c in optional) if optional else ""
        validation_block = f"""

**Validation criteria (validate before Finish using task-output-validator skill):**
{criteria_text}
{optional_text}
"""

    user_prompt = f"""**Task ID:** {task_id}
**Description:** {description}

**Input description:** {input_desc}
**Input artifacts:**
```json
{inputs_str}
```

**Output description:** {output_desc}
**Output format:** {output_format}
{validation_block}

Produce the output now. Output ONLY the result, no explanation."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return messages, output_format


async def run_task_agent(
    task_id: str,
    description: str,
    input_spec: Dict[str, Any],
    output_spec: Dict[str, Any],
    resolved_inputs: Dict[str, Any],
    api_config: Dict[str, Any],
    abort_event: Optional[Any],
    on_thinking: Optional[Callable[[str, Optional[str], Optional[str]], None]],
    plan_id: str,
    validation_spec: Optional[Dict[str, Any]] = None,
) -> Any:
    """ReAct-style Agent loop with ReadArtifact, ReadFile, Finish tools. Runs in isolated sandbox."""
    if plan_id and task_id:
        await ensure_sandbox_dir(plan_id, task_id)
    messages, output_format = _build_task_agent_messages(
        task_id, description, input_spec, output_spec, resolved_inputs, validation_spec
    )
    use_json_mode = _is_json_format(output_format)
    cfg = merge_phase_config(api_config, "execute")
    max_turns, temperature = _get_task_agent_params(api_config)
    turn = 0

    while turn < max_turns:
        turn += 1
        if abort_event and abort_event.is_set():
            raise asyncio.CancelledError("Execution aborted")

        result = await chat_completion(
            messages,
            cfg,
            on_chunk=None,
            abort_event=abort_event,
            stream=False,
            temperature=temperature,
            response_format=None,
            tools=TOOLS,
        )

        content: str
        if isinstance(result, dict):
            raw_content = result.get("content") or ""
            content = raw_content if isinstance(raw_content, str) else str(raw_content)
        else:
            content = result or ""

        schedule_info = {"turn": turn, "max_turns": max_turns}
        if on_thinking and content:
            r = on_thinking(content, task_id=task_id, operation="Execute", schedule_info=schedule_info)
            if asyncio.iscoroutine(r):
                await r

        if isinstance(result, dict) and result.get("finish_reason") == "tool_calls":
            tool_calls = result.get("tool_calls") or []
            if not tool_calls:
                content = content or "(no content)"
                return _parse_task_agent_output(content, use_json_mode)

            sig_from_any = None
            for tc in tool_calls:
                s = tc.get("thought_signature") or tc.get("thoughtSignature")
                if s is not None:
                    sig_from_any = s
                    break

            assistant_msg = {"role": "assistant", "content": content or None}
            tool_calls_for_msg = []
            for i, tc in enumerate(tool_calls):
                entry = {
                    "id": tc.get("id", f"tc_{i}"),
                    "type": tc.get("type", "function"),
                    "function": tc.get("function", {}),
                }
                sig = tc.get("thought_signature") or tc.get("thoughtSignature") or (sig_from_any if i == 0 else None)
                if sig is not None:
                    entry["thought_signature"] = sig
                tool_calls_for_msg.append(entry)
            tool_calls_for_msg = [tc for tc in tool_calls_for_msg if tc.get("function")]
            if tool_calls_for_msg:
                assistant_msg["tool_calls"] = tool_calls_for_msg
            if result.get("gemini_model_content") is not None:
                assistant_msg["gemini_model_content"] = result["gemini_model_content"]
            messages.append(assistant_msg)

            finished_output = None
            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                args = fn.get("arguments") or "{}"
                if on_thinking:
                    tool_schedule = {"turn": turn, "max_turns": max_turns, "tool_name": name, "tool_args": (args[:200] + "...") if len(args) > 200 else args}
                    r = on_thinking("", task_id=task_id, operation="Execute", schedule_info=tool_schedule)
                    if asyncio.iscoroutine(r):
                        await r
                try:
                    out, tool_result = await execute_tool(name, args, plan_id, task_id)
                except Exception as e:
                    tool_result = f"Error: {e}"

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": tool_result,
                    }
                )

                if out is not None:
                    finished_output = out
                    break

            if finished_output is not None:
                return finished_output
            continue

        return _parse_task_agent_output(content, use_json_mode)

    last = ""
    for m in reversed(messages):
        if m.get("role") == "assistant" and m.get("content"):
            last = m["content"]
            break
    if not last:
        raise ValueError(f"Agent reached max turns ({max_turns}) without producing output")
    return _parse_task_agent_output(last, use_json_mode)
