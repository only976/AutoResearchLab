"""
Task output validation - LLM-based validation. Used in LLM mode only.
Agent mode uses task-output-validator skill instead.
"""

import json
from typing import Any, Dict, Optional, Tuple

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


async def validate_task_output_with_llm(
    result: Any,
    output_spec: Dict[str, Any],
    task_id: str,
    validation_spec: Optional[Dict[str, Any]] = None,
    api_config: Optional[Dict] = None,
    abort_event: Optional[Any] = None,
) -> Tuple[bool, str]:
    """
    Use LLM to validate task output against criteria.
    Returns (passed, report_markdown).
    Called only in LLM mode; Agent mode uses task-output-validator skill.
    """
    content = _get_content_str(result)
    validation = validation_spec or {}
    criteria = validation.get("criteria") or []
    output_format = (output_spec or {}).get("format") or ""

    system_prompt = """You are a validation assistant. Judge whether the task output meets the validation criteria.
Respond with a JSON object: {"passed": true|false, "report": "markdown string"}.
The report should list each criterion and PASS/FAIL, then a final Result line."""

    criteria_text = "\n".join(f"- {c}" for c in criteria) if criteria else "Output should be complete and align with the task description."
    user_message = f"""Task ID: {task_id}
Output format expected: {output_format}

Validation criteria:
{criteria_text}

Task output to validate:
```
{content[:8000]}
```

Respond with JSON: {{"passed": true|false, "report": "markdown report"}}"""

    try:
        cfg = merge_phase_config(api_config or {}, "validate")
        response = await chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            cfg,
            on_chunk=None,
            abort_event=abort_event,
            stream=False,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        text = response if isinstance(response, str) else (response.get("content") or "")
        parsed = json.loads(text) if isinstance(text, str) else {}
        passed = bool(parsed.get("passed"))
        report = parsed.get("report") or f"# Validating Task {task_id}\n\n**Result: {'PASS' if passed else 'FAIL'}** (LLM validation)"
        return passed, report
    except Exception as e:
        report = f"# Validating Task {task_id}\n\n**Result: FAIL**\n\nLLM validation error: {e}"
        return False, report
