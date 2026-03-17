"""
Task output validation - LLM-based validation. Used in LLM mode only.
Agent mode uses task-output-validator skill instead.
Supports streaming via on_chunk for real-time Thinking display.
"""

import asyncio
import json
import re
from typing import Any, Callable, Dict, Optional, Tuple

from shared.constants import TEMP_DETERMINISTIC
from shared.llm_client import chat_completion, merge_phase_config


def _get_content_str(result: Any) -> str:
    """Extract content as string for validation."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        if "content" in result:
            c = result["content"]
            return c if isinstance(c, str) else json.dumps(c)
        return json.dumps(result)
    return str(result)


# L1: Execution-mode structural mismatch — the current delivery channel is fundamentally
# incapable of producing the artifact form required by the contract (e.g., returning a live
# sklearn Pipeline via a JSON text channel).
_CONTRACT_MISMATCH_MARKERS = (
    "cannot be serialized to json",
    "not json-serializable",
    "live python object",
    "live sklearn",
    "live model instance",
    "live pipeline instance",
    "in-memory object cannot",
    "in-memory model",
    "requires pickling",
    "requires live",
    "not a serializable",
    "cannot serialize the pipeline",
    "cannot serialize the model",
    "delivery mode mismatch",
    "mode cannot produce",
    # File-path vs. in-memory object: task returned a file path when the contract
    # requires an in-memory object (ndarray, DataFrame, etc.). This is a structural
    # delivery-mode mismatch, not a transient failure — reframe is the right action.
    "string path instead of",
    "file path instead of",
    "file paths instead of",
    "only file paths provided",
    "provided as a string path",
    "path instead of ndarray",
    "path instead of array",
    "path instead of dataframe",
    "received string path",
    "received file path",
)
def classify_validation_failure(report: str, output_format: str = "") -> dict:
    """Best-effort local classification for retry policy decisions."""
    text = f"{output_format}\n{report or ''}".lower()
    if not text.strip():
        return {"category": "semantic", "retryable": True}

    terminal_markers = (
        "cannot be implemented",
        "not feasible",
        "infeasible",
        "unachievable",
        "impossible under",
        "objective is impossible",
    )
    if any(marker in text for marker in terminal_markers):
        return {"category": "terminal_unachievable", "retryable": False}

    # L1: execution-mode structural mismatch (detected by explicit signal in report)
    if any(marker in text for marker in _CONTRACT_MISMATCH_MARKERS):
        return {"category": "contract_mismatch", "retryable": True}

    format_markers = (
        "failed to parse",
        "invalid json",
        "expected numerical array",
        "expected numerical array/time-series",
        "expected numerical array or time-series object",
        "received text description",
        "received metadata json",
        "output format: fail",
        "prose-only",
        "content wrapper",
    )
    evidence_markers = (
        "data not provided",
        "no data provided",
        "no spectral analysis or data provided",
        "claimed match, but data not provided",
        "no visual or quantitative evidence provided",
        "no n/a",
    )

    if any(marker in text for marker in format_markers):
        return {"category": "format", "retryable": True}
    if any(marker in text for marker in evidence_markers):
        return {"category": "evidence_missing", "retryable": True}
    return {"category": "semantic", "retryable": True}
async def validate_task_output_with_llm(
    result: Any,
    output_spec: Dict[str, Any],
    task_id: str,
    validation_spec: Optional[Dict[str, Any]] = None,
    api_config: Optional[Dict] = None,
    abort_event: Optional[Any] = None,
    on_thinking: Optional[Callable[[str, Optional[str], Optional[str], Optional[dict]], None]] = None,
) -> Tuple[bool, str]:
    """
    Use LLM to validate task output against criteria.
    Returns (passed, report_markdown).
    Called only in LLM mode; Agent mode uses task-output-validator skill.
    When on_thinking provided, streams LLM output for real-time Thinking display.
    """
    content = _get_content_str(result)
    validation = validation_spec or {}
    criteria = validation.get("criteria") or []
    output_format = (output_spec or {}).get("format") or ""

    system_prompt = (
        "You are a validation assistant. Judge whether the task output meets the validation criteria.\n\n"
        "Output in two parts:\n"
        "1. **Reasoning** (1-2 sentences): Briefly explain your validation analysis. This will be shown as your thinking process.\n"
        "2. **JSON**: Output a JSON block in ```json and ``` with: {\"passed\": true|false, \"report\": \"markdown string\"}\n"
        "The report should list each criterion and PASS/FAIL, then a final Result line."
    )

    criteria_text = "\n".join(f"- {c}" for c in criteria) if criteria else "Output should be complete and align with the task description."
    user_message = f"""Task ID: {task_id}
Output format expected: {output_format}

Validation criteria:
{criteria_text}

Task output to validate:
```
{content[:8000]}
```

Output your reasoning first, then the JSON block."""

    def _stream_chunk(chunk: str):
        """转发 chunk 到 on_thinking，若为 async 则返回 coroutine 供 chat_completion await。"""
        if on_thinking and chunk:
            r = on_thinking(chunk, task_id=task_id, operation="Validate", schedule_info=None)
            if asyncio.iscoroutine(r):
                return r

    try:
        cfg = merge_phase_config(api_config or {}, "validate")
        stream = on_thinking is not None
        # 不使用 response_format，以便 LLM 先输出 reasoning 再输出 JSON（Thinking 显示推理）
        response = await chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            cfg,
            on_chunk=_stream_chunk if stream else None,
            abort_event=abort_event,
            stream=stream,
            temperature=TEMP_DETERMINISTIC,
        )
        text = response if isinstance(response, str) else (response.get("content") or "")
        # 从 reasoning + ```json...``` 中提取 JSON，若无代码块则尝试整体解析
        cleaned = (text or "").strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
        if m:
            cleaned = m.group(1).strip()
        try:
            parsed = json.loads(cleaned) if cleaned else {}
        except (json.JSONDecodeError, TypeError):
            parsed = {}
        passed = bool(parsed.get("passed"))
        report = parsed.get("report") or f"# Validating Task {task_id}\n\n**Result: {'PASS' if passed else 'FAIL'}** (LLM validation)"
        return passed, report
    except Exception as e:
        report = f"# Validating Task {task_id}\n\n**Result: FAIL**\n\nLLM validation error: {e}"
        return False, report


async def validate_task_output_with_readonly_agent(
    result: Any,
    output_spec: Dict[str, Any],
    task_id: str,
    validation_spec: Optional[Dict[str, Any]] = None,
    validation_context: Optional[Dict[str, Any]] = None,
    api_config: Optional[Dict] = None,
    abort_event: Optional[Any] = None,
    on_thinking: Optional[Callable[[str, Optional[str], Optional[str], Optional[dict]], None]] = None,
) -> Tuple[bool, str]:
    """Read-only validation agent.

    This validator is intentionally isolated from execution concerns:
    it can reason from provided context and output content only,
    and must not propose file writes or command execution.
    """
    content = _get_content_str(result)
    validation = validation_spec or {}
    criteria = validation.get("criteria") or []
    output_format = (output_spec or {}).get("format") or ""
    context = validation_context or {}

    system_prompt = (
        "You are a READ-ONLY validation agent.\n"
        "You are not allowed to execute commands, write files, or call tools.\n"
        "Use only provided task context, attempt history, and output content to judge criteria.\n\n"
        "Equivalent-format policy:\n"
        "- If criteria explicitly allow equivalent representation (for example XML<->JSON, matrix<->CSV), "
        "you may pass only when output provides verifiable equivalence evidence (conversion method, source/target, checks).\n"
        "- If evidence is missing, fail the relevant criteria.\n\n"
        "Output in two parts:\n"
        "1. **Reasoning** (1-2 sentences): Briefly explain your validation analysis.\n"
        "2. **JSON**: Output a JSON block in ```json and ``` with: {\"passed\": true|false, \"report\": \"markdown string\"}\n"
        "The report should list each criterion and PASS/FAIL, then a final Result line."
    )

    criteria_text = "\n".join(f"- {c}" for c in criteria) if criteria else "Output should be complete and align with the task description."
    context_text = json.dumps(context, ensure_ascii=False)[:4000]
    user_message = f"""Task ID: {task_id}
Output format expected: {output_format}

Validation context (read-only):
```json
{context_text}
```

Validation criteria:
{criteria_text}

Task output to validate:
```
{content[:8000]}
```

Output your reasoning first, then the JSON block."""

    def _stream_chunk(chunk: str):
        if on_thinking and chunk:
            r = on_thinking(chunk, task_id=task_id, operation="Validate", schedule_info=None)
            if asyncio.iscoroutine(r):
                return r

    try:
        cfg = merge_phase_config(api_config or {}, "validate")
        stream = on_thinking is not None
        response = await chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            cfg,
            on_chunk=_stream_chunk if stream else None,
            abort_event=abort_event,
            stream=stream,
            temperature=TEMP_DETERMINISTIC,
        )
        text = response if isinstance(response, str) else (response.get("content") or "")
        cleaned = (text or "").strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
        if m:
            cleaned = m.group(1).strip()
        try:
            parsed = json.loads(cleaned) if cleaned else {}
        except (json.JSONDecodeError, TypeError):
            parsed = {}
        passed = bool(parsed.get("passed"))
        report = parsed.get("report") or f"# Validating Task {task_id}\n\n**Result: {'PASS' if passed else 'FAIL'}** (Read-only validation agent)"
        return passed, report
    except Exception as e:
        report = f"# Validating Task {task_id}\n\n**Result: FAIL**\n\nRead-only validation agent error: {e}"
        return False, report
