"""
Task Agent - Google ADK 驱动实现。
当 taskAgentMode=True 时使用，替代自实现 ReAct 循环。
"""

import json
import math
import re
from typing import Any, Callable, Dict, Optional

import json_repair

from db import ensure_execution_task_dirs, ensure_sandbox_dir
from shared.adk_bridge import (
    create_executor_tools,
    get_model_for_adk,
    prepare_api_env,
)
from shared.adk_runtime import (
    build_tool_args_preview,
    run_adk_agent_loop,
)
from shared.constants import TASK_AGENT_MAX_TURNS
from shared.constants import (
    TASK_AGENT_CONTEXT_HARD_LIMIT_TOKENS,
    TASK_AGENT_CONTEXT_TARGET_TOKENS,
    TEMP_STRUCTURED,
)
from shared.llm_client import chat_completion, merge_phase_config

from .agent_tools import TOOLS, execute_tool


def _is_json_format(output_format: str) -> bool:
    if not output_format:
        return False
    fmt = output_format.strip().upper()
    return fmt.startswith("JSON") or "JSON" in fmt


def _parse_task_agent_output(content: str, use_json_mode: bool) -> Any:
    """Parse Task Agent output to final result."""
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


def _estimate_tokens(text: str) -> int:
    # Rule-of-thumb estimate (works for budget control without model tokenizer dependency).
    return max(1, math.ceil(len(text or "") / 4))


def _truncate_string(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    kept = max(0, max_chars - 64)
    head = value[:kept]
    return f"{head}\n...[truncated {len(value) - kept} chars]"


def _safe_json_loads(raw: str) -> Any:
    try:
        return json_repair.loads(raw)
    except Exception:
        return None


def _validate_compressed_object_shape(original: Any, compressed: Any, label: str) -> tuple[bool, str]:
    if compressed is None:
        return False, "compressed payload is None"
    if label in ("resolved_inputs", "execution_context"):
        if isinstance(original, dict) and isinstance(compressed, dict):
            # keep critical top-level keys when present
            for key in ("globalGoal", "planContext", "taskContract", "retryMemory"):
                if key in original and key not in compressed:
                    return False, f"missing required top-level key: {key}"
            return True, "ok"
        if isinstance(original, dict) and not isinstance(compressed, dict):
            return False, "compressed payload must remain object for dict input"
    return True, "ok"


async def _compress_object_with_llm(
    value: Any,
    *,
    label: str,
    target_tokens: int,
    api_config: Dict[str, Any],
    abort_event: Optional[Any],
) -> tuple[Any, dict]:
    import orjson

    if value is None:
        return value, {
            "mode": "empty",
            "originalTokensEst": 0,
            "compressedTokensEst": 0,
            "valid": True,
        }

    try:
        original_text = orjson.dumps(value, option=orjson.OPT_INDENT_2).decode("utf-8")
    except Exception:
        original_text = str(value)
    original_tokens = _estimate_tokens(original_text)

    if original_tokens <= target_tokens:
        return value, {
            "mode": "passthrough",
            "originalTokensEst": original_tokens,
            "compressedTokensEst": original_tokens,
            "valid": True,
        }

    llm_cfg = merge_phase_config(api_config or {}, phase="task")
    llm_cfg["temperature"] = TEMP_STRUCTURED

    system_prompt = (
        "You are a strict JSON context compressor. "
        "Compress large JSON context while preserving task-critical semantics. "
        "Output JSON only."
    )
    user_prompt = f"""
Label: {label}
Target token budget: <= {target_tokens}

Return JSON object with exact shape:
{{
  "compressed": <json object/array/string>,
  "notes": ["short note", "..."]
}}

Rules:
1) Preserve goals, constraints, task contract, retry failures, and actionable next steps.
2) Remove repetitive logs and oversized raw payloads by replacing them with concise semantic summaries.
3) Keep keys stable when possible.
4) Never output markdown.

Input JSON:
{original_text}
"""

    try:
        resp = await chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            llm_cfg,
            abort_event=abort_event,
            stream=False,
            response_format={"type": "json_object"},
            temperature=TEMP_STRUCTURED,
        )
        parsed = _safe_json_loads(str(resp or "")) if not isinstance(resp, dict) else resp
        compressed = (parsed or {}).get("compressed") if isinstance(parsed, dict) else None
        ok, reason = _validate_compressed_object_shape(value, compressed, label)
        if ok:
            try:
                compressed_text = orjson.dumps(compressed, option=orjson.OPT_INDENT_2).decode("utf-8")
            except Exception:
                compressed_text = str(compressed)
            return compressed, {
                "mode": "llm",
                "originalTokensEst": original_tokens,
                "compressedTokensEst": _estimate_tokens(compressed_text),
                "valid": True,
                "reason": "ok",
            }
        fallback = _shrink_for_prompt(value, max_depth=5, max_items=40, max_str_chars=1800)
        try:
            fallback_text = orjson.dumps(fallback, option=orjson.OPT_INDENT_2).decode("utf-8")
        except Exception:
            fallback_text = str(fallback)
        return fallback, {
            "mode": "fallback",
            "originalTokensEst": original_tokens,
            "compressedTokensEst": _estimate_tokens(fallback_text),
            "valid": False,
            "reason": reason,
        }
    except Exception as e:
        fallback = _shrink_for_prompt(value, max_depth=5, max_items=40, max_str_chars=1800)
        try:
            fallback_text = orjson.dumps(fallback, option=orjson.OPT_INDENT_2).decode("utf-8")
        except Exception:
            fallback_text = str(fallback)
        return fallback, {
            "mode": "fallback",
            "originalTokensEst": original_tokens,
            "compressedTokensEst": _estimate_tokens(fallback_text),
            "valid": False,
            "reason": f"llm_error: {e}",
        }


def _shrink_for_prompt(value: Any, *, max_depth: int, max_items: int, max_str_chars: int) -> Any:
    if max_depth < 0:
        return "[truncated: max depth reached]"
    if isinstance(value, dict):
        out = {}
        for idx, (key, val) in enumerate(value.items()):
            if idx >= max_items:
                out["__truncated_keys__"] = f"{len(value) - max_items} more keys"
                break
            out[str(key)] = _shrink_for_prompt(
                val,
                max_depth=max_depth - 1,
                max_items=max_items,
                max_str_chars=max_str_chars,
            )
        return out
    if isinstance(value, list):
        out = []
        for idx, item in enumerate(value):
            if idx >= max_items:
                out.append(f"[truncated: {len(value) - max_items} more items]")
                break
            out.append(
                _shrink_for_prompt(
                    item,
                    max_depth=max_depth - 1,
                    max_items=max_items,
                    max_str_chars=max_str_chars,
                )
            )
        return out
    if isinstance(value, str):
        return _truncate_string(value, max_str_chars)
    return value


def _render_json_block(value: Any, *, max_chars: int) -> tuple[str, dict]:
    import orjson

    try:
        original = orjson.dumps(value, option=orjson.OPT_INDENT_2).decode("utf-8")
    except Exception:
        original = str(value)
    original_tokens = _estimate_tokens(original)

    shaped = _shrink_for_prompt(value, max_depth=5, max_items=40, max_str_chars=1800)
    try:
        text = orjson.dumps(shaped, option=orjson.OPT_INDENT_2).decode("utf-8")
    except Exception:
        text = str(shaped)

    if len(text) > max_chars:
        text = _truncate_string(text, max_chars)

    info = {
        "originalChars": len(original),
        "compressedChars": len(text),
        "originalTokensEst": original_tokens,
        "compressedTokensEst": _estimate_tokens(text),
        "truncated": len(text) < len(original),
    }
    return text, info


def _build_system_prompt(
    output_format: str,
    validation_spec: Optional[Dict[str, Any]] = None,
    idea_context: str = "",
) -> str:
    """构建 Task Agent 的 system prompt。"""
    validation_rule = ""
    if validation_spec and (validation_spec.get("criteria") or validation_spec.get("optionalChecks")):
        validation_rule = """
5. **Validation (required when task has validation spec)**: Before calling Finish, you MUST validate your output. Load the task-output-validator skill, write output to sandbox (e.g. sandbox/output.json or sandbox/result.md), run its validate script with the validation criteria, fix any failures, then call Finish only when validation passes."""

    idea_block = ""
    if idea_context:
        idea_block = f"\n6. **Research context**: This task is part of a larger research project. The overarching research idea is provided below — use it to ensure your output aligns with the project goals and maintains consistency."

    return f"""You are a Task Agent. Your job is to complete a single atomic task and produce output in the exact format specified.

Rules:
1. Use only the provided input artifacts and task description.
2. Output must strictly conform to the specified format.
3. Before calling any tool, briefly explain your reasoning: what you know, what you need, and why you are choosing this tool. This reasoning will be shown as your thinking process.
4. For JSON: output valid JSON when calling Finish; for Markdown, pass the document content.{validation_rule}{idea_block}
5. Minimize tool calls. Once you have enough information to produce a correct answer, stop exploring and call Finish immediately.
6. Do not repeat the same search/read action unless the previous result was clearly insufficient.
7. In execution mode, sandbox paths map to the shared execution source directory (`/workdir/src`). This directory can contain files generated by upstream tasks in the same execution run.
8. If you are unsure what files exist, call ListFiles on `sandbox/` first, then ReadFile only the relevant files.

You have tools: ReadArtifact (read dependency task output), ListFiles (discover available files/directories), ReadFile (read files; use 'sandbox/X' paths), WriteFile (write only under sandbox), RunCommand (run shell commands inside the local Docker execution container using `/workdir/src`), ListSkills, LoadSkill, ReadSkillFile (read skill's scripts/references), RunSkillScript (execute skill scripts, use sandbox/file style paths for sandbox arguments), WebSearch (search the web for research—use for benchmarks, docs, current data), WebFetch (fetch URL content for citations), Finish (submit final output).
Use ListSkills to discover skills, LoadSkill when relevant. Common task types: literature synthesis → literature-synthesis; comparison report → comparison-report; validation required → task-output-validator. ReadSkillFile and RunSkillScript let you use skill capabilities (e.g. docx validate, pptx convert). Use RunCommand when you need to create files, run Python or shell scripts, or inspect generated artifacts inside Docker. When your output satisfies the output spec, you MUST call Finish with the result—do not output inline. For JSON format pass a valid JSON string; for Markdown pass the content string. All execution file I/O is scoped to this task's sandbox inside its container."""


def _build_user_message(
    *,
    task_id: str,
    description: str,
    input_spec: Dict[str, Any],
    resolved_inputs: Dict[str, Any],
    output_spec: Dict[str, Any],
    output_format: str,
    validation_spec: Optional[Dict[str, Any]] = None,
    idea_context: str = "",
    execution_context: Optional[Dict[str, Any]] = None,
) -> tuple[str, dict]:
    inputs_str = "No input artifacts."
    inputs_stats = {"originalChars": 0, "compressedChars": 0, "originalTokensEst": 0, "compressedTokensEst": 0, "truncated": False}
    if resolved_inputs:
        inputs_str, inputs_stats = _render_json_block(resolved_inputs, max_chars=120000)

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

    idea_section = ""
    if idea_context:
        idea_section = f"\n**Research idea (project context):** {idea_context}\n"

    execution_context_block = ""
    execution_stats = {"originalChars": 0, "compressedChars": 0, "originalTokensEst": 0, "compressedTokensEst": 0, "truncated": False}
    if execution_context:
        context_json, execution_stats = _render_json_block(execution_context, max_chars=120000)
        execution_context_block = f"""

**Execution context (global + plan + task + retry memory):**
```json
{context_json}
```
Use this context to avoid repeating previous failed attempts and to focus on the shortest path to a valid output.
"""

    message = f"""**Task ID:** {task_id}
**Description:** {description}
{idea_section}
**Input description:** {input_spec.get("description", "")}
**Input artifacts:**
```json
{inputs_str}
```

**Output description:** {output_spec.get("description", "")}
**Output format:** {output_format}
{validation_block}
{execution_context_block}

**Execution filesystem semantics:**
- Use `sandbox/...` paths for all execution file operations.
- `sandbox/` is the shared execution source directory for this run (mounted at `/workdir/src`).
- Per-task runtime traces are stored under step directories and are not the primary output location.
- `RunCommand` executes with `/workdir/src` as cwd: run `python3 load_datasets.py` (not `python3 sandbox/load_datasets.py`).

Produce the output now. You may reason first; when ready, call Finish with the result."""

    target_tokens = max(10000, min(TASK_AGENT_CONTEXT_TARGET_TOKENS, 30000))
    hard_tokens = max(50000, TASK_AGENT_CONTEXT_HARD_LIMIT_TOKENS)
    hard_chars = hard_tokens * 4
    target_chars = target_tokens * 4
    if len(message) > hard_chars:
        message = _truncate_string(message, hard_chars)
    if len(message) > target_chars:
        # Preserve main instruction but trim long tails further.
        message = _truncate_string(message, target_chars)

    budget = {
        "targetTokens": target_tokens,
        "hardLimitTokens": hard_tokens,
        "finalTokensEst": _estimate_tokens(message),
        "finalChars": len(message),
        "inputs": inputs_stats,
        "executionContext": execution_stats,
    }
    return message, budget


async def run_task_agent_adk(
    task_id: str,
    description: str,
    input_spec: Dict[str, Any],
    output_spec: Dict[str, Any],
    resolved_inputs: Dict[str, Any],
    api_config: Dict[str, Any],
    abort_event: Optional[Any],
    on_thinking: Optional[Callable[[str, Optional[str], Optional[str]], None]],
    idea_id: str,
    plan_id: str,
    execution_run_id: str = "",
    docker_container_name: str = "",
    validation_spec: Optional[Dict[str, Any]] = None,
    idea_context: str = "",
    execution_context: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    使用 Google ADK Runner 运行 Task Agent。
    返回任务输出 (dict 或 str)。
    """
    prepare_api_env(api_config)

    if idea_id and plan_id and task_id and execution_run_id:
        await ensure_execution_task_dirs(execution_run_id, task_id)
    elif idea_id and plan_id and task_id:
        await ensure_sandbox_dir(idea_id, plan_id, task_id)

    output_format = output_spec.get("format") or ""
    use_json_mode = _is_json_format(output_format)
    on_thinking_fn = on_thinking or (lambda *a, **_: None)

    compressed_inputs, _inputs_compress_meta = await _compress_object_with_llm(
        resolved_inputs,
        label="resolved_inputs",
        target_tokens=max(4000, int(TASK_AGENT_CONTEXT_TARGET_TOKENS * 0.45)),
        api_config=api_config,
        abort_event=abort_event,
    )
    compressed_execution_context, _context_compress_meta = await _compress_object_with_llm(
        execution_context,
        label="execution_context",
        target_tokens=max(3000, int(TASK_AGENT_CONTEXT_TARGET_TOKENS * 0.35)),
        api_config=api_config,
        abort_event=abort_event,
    )

    task_output: list = [None]
    async def executor_fn(name: str, args: dict) -> tuple[bool, str]:
        args_str = json.dumps(args, ensure_ascii=False)
        out, tool_result = await execute_tool(
            name,
            args_str,
            idea_id,
            plan_id,
            task_id,
            execution_run_id=execution_run_id,
            docker_container_name=docker_container_name,
        )
        if out is not None:
            task_output[0] = out
            return True, '{"status": "success", "message": "Task completed."}'
        return False, tool_result

    tools = create_executor_tools(TOOLS, executor_fn)
    system_prompt = _build_system_prompt(output_format, validation_spec, idea_context)

    user_message, _context_budget = _build_user_message(
        task_id=task_id,
        description=description,
        input_spec=input_spec,
        resolved_inputs=compressed_inputs,
        output_spec=output_spec,
        output_format=output_format,
        validation_spec=validation_spec,
        idea_context=idea_context,
        execution_context=compressed_execution_context,
    )

    model = get_model_for_adk(api_config)

    def _on_tool_call(name: str, args: dict, turn_count: int, token_usage: Optional[dict] = None):
        # Use real ADK turn count so UI reflects actual agent execution progression.
        display_turn = turn_count
        args_preview = build_tool_args_preview(args, max_len=150)
        tool_msg = f"Calling {name}({args_preview})"
        return on_thinking_fn(
            tool_msg,
            task_id=task_id,
            operation="Execute",
            schedule_info={
                "turn": display_turn,
                "max_turns": TASK_AGENT_MAX_TURNS,
                "tool_name": name,
                "tool_args": build_tool_args_preview(args),
                "tool_args_preview": None,
                "operation": "Execute",
                "task_id": task_id,
                "token_usage": token_usage or {},
            },
        )

    def _on_text(text: str, turn_count: int, token_usage: Optional[dict] = None):
        display_turn = turn_count
        return on_thinking_fn(
            text,
            task_id=task_id,
            operation="Execute",
            schedule_info={
                "turn": display_turn,
                "max_turns": TASK_AGENT_MAX_TURNS,
                "operation": "Execute",
                "task_id": task_id,
                "token_usage": token_usage or {},
            },
        )

    await run_adk_agent_loop(
        app_name="maars_task",
        agent_name="task_agent",
        model=model,
        instruction=system_prompt,
        tools=tools,
        user_message=user_message,
        max_turns=TASK_AGENT_MAX_TURNS,
        abort_event=abort_event,
        abort_message="Task Agent aborted",
        on_tool_call=_on_tool_call,
        on_text=_on_text,
    )

    if task_output[0] is not None:
        return task_output[0]

    raise ValueError(
        f"Agent reached max turns ({TASK_AGENT_MAX_TURNS}) without calling Finish"
    )
