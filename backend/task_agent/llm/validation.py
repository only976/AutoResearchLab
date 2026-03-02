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

    system_prompt = """You are a validation assistant. Judge whether the task output meets the validation criteria.

Output in two parts:
1. **Reasoning** (1-2 sentences): Briefly explain your validation analysis. This will be shown as your thinking process.
2. **JSON**: Output a JSON block in ```json and ``` with: {"passed": true|false, "report": "markdown string"}
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
