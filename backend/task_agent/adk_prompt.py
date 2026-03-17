"""
Prompt building utilities for the Task Agent ADK runner.
"""

import math
import re
from typing import Any, Dict, Optional

from shared.constants import (
    TASK_AGENT_CONTEXT_HARD_LIMIT_TOKENS,
    TASK_AGENT_CONTEXT_TARGET_TOKENS,
)


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text or "") / 4))


def _truncate_string(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    kept = max(0, max_chars - 64)
    head = value[:kept]
    return f"{head}\n...[truncated {len(value) - kept} chars]"


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
4. For JSON: output valid JSON when calling Finish; for Markdown, pass the document content.
     - JSON is serialization-only: do NOT claim to return live in-memory Python objects directly.
    - For non-Markdown structured outputs (arrays, tables, objects, time-series), call Finish with a JSON-serializable structured payload, not a prose summary.
     - If task asks for "initialized objects/instances", return a JSON-serializable representation that is runnable in downstream steps, e.g.:
         a) class/import path + constructor params, and/or
         b) path to serialized artifacts (such as .pkl/.joblib) written under sandbox/.
     - If task asks for arrays/tensors (e.g., NumPy ndarray X/y), return loadable artifact references and metadata:
         a) artifact paths (.npy/.npz),
         b) keys for .npz,
         c) shape/dtype/sample-count consistency fields,
         d) optional validation summary (numeric/no NaN/Inf).
     - Prefer outputs that downstream code can load and call `.fit()` with minimal glue code.{validation_rule}{idea_block}
5. Minimize tool calls. Once you have enough information to produce a correct answer, stop exploring and call Finish immediately.
6. Do not repeat the same search/read action unless the previous result was clearly insufficient.
7. In execution mode, sandbox paths map to the shared execution source directory (`/workdir/src`). This directory can contain files generated by upstream tasks in the same execution run.
8. If you are unsure what files exist, call ListFiles on `sandbox/` first, then ReadFile only the relevant files.
9. If retryMemory is provided, you MUST address its lastFailure explicitly before major tool execution. Start by stating what failed last time and what is different in this attempt.
10. Repeating the same failure pattern from retryMemory.lastFailure is a hard violation. If last failure mentions output format mismatch (e.g. JSON metadata/path instead of required matrix/object), you must return the required artifact form directly in Finish output.
11. If you adapt validation criteria due to equivalent data representations (for example XML<->JSON or matrix<->CSV), you MUST produce explicit equivalence evidence in the output (method, source/target paths, checks performed, pass/fail summary) so downstream validation can verify the adaptation.

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
    retry_guardrails_block = ""
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

        retry_memory = execution_context.get("retryMemory") if isinstance(execution_context, dict) else None
        if isinstance(retry_memory, dict) and retry_memory:
            last_failure = str(retry_memory.get("lastFailure") or "").strip()
            retry_guardrails_block = f"""

**Retry guardrails (MANDATORY for this attempt):**
- Last failure you must avoid repeating:
  {last_failure or "(not provided)"}
- Before major tool execution, explain what changed versus the failed attempt.
- Your final `Finish` output MUST directly satisfy the required output format; do not return only file paths or metadata when raw data/object is required.
- If using equivalent-format adaptation (XML/JSON, matrix/CSV), include equivalence evidence in output: conversion method, compared artifacts, and verification results.
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
{retry_guardrails_block}

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
