"""
Paper Agent implementation.

- Mock mode: stream fixed output from test/mock-ai/paper.json
- LLM mode: single-pass full paper drafting
- Agent mode: outline -> section drafting -> assembly MVP
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import orjson
from loguru import logger

from shared.llm_client import chat_completion, merge_phase_config
from test.mock_stream import mock_chat_completion

PAPER_DIR = Path(__file__).resolve().parent
MOCK_AI_DIR = PAPER_DIR.parent / "test" / "mock-ai"
MOCK_KEY = "_default"

_mock_cache: Dict[str, dict] = {}


async def _emit_thinking(on_thinking: Optional[Callable[..., Any]], chunk: str, operation: str = "Paper") -> None:
    if not on_thinking or not chunk:
        return
    r = on_thinking(chunk, None, operation, None)
    if hasattr(r, "__await__"):
        await r


def _truncate_text(value: Any, limit: int = 1200) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _get_mock_cached() -> dict:
    if "paper" not in _mock_cache:
        path = MOCK_AI_DIR / "paper.json"
        try:
            _mock_cache["paper"] = orjson.loads(path.read_bytes())
        except (FileNotFoundError, orjson.JSONDecodeError):
            _mock_cache["paper"] = {}
    return _mock_cache["paper"]


def _load_mock_response() -> Optional[Dict]:
    """从 test/mock-ai/paper.json 加载 mock，与 idea/plan 对齐。"""
    data = _get_mock_cached()
    entry = data.get(MOCK_KEY) or data.get("_default")
    if not entry:
        return None
    content = entry.get("content")
    if isinstance(content, str):
        content_str = content
    else:
        content_str = orjson.dumps(content).decode("utf-8")
    return {"content": content_str, "reasoning": entry.get("reasoning", "")}


def _maars_plan_to_paper_format(plan: dict) -> dict:
    """Convert MAARS plan shape to writing prompt format."""
    tasks = plan.get("tasks") or []
    return {
        "title": plan.get("idea") or "Untitled",
        "goal": plan.get("idea") or "N/A",
        "steps": [{"description": t.get("description", "")} for t in tasks],
    }


def _synthesize_conclusion_from_outputs(outputs: dict) -> dict:
    """Build conclusion dict from MAARS task outputs for paper draft."""
    findings = []
    for task_id, out in outputs.items():
        if isinstance(out, dict):
            content = out.get("content") or out.get("summary") or str(out)[:500]
            findings.append(f"Task {task_id}: {content}")
        else:
            findings.append(f"Task {task_id}: {str(out)[:500]}")
    return {
        "summary": "Synthesized from task outputs.",
        "key_findings": findings[:10],
        "recommendation": "Review and refine based on full task outputs.",
    }


def _build_output_digest(outputs: dict) -> list[dict]:
    digest = []
    for task_id, out in (outputs or {}).items():
        if isinstance(out, dict):
            content = out.get("content") or out.get("summary") or json.dumps(out, ensure_ascii=False)
        else:
            content = str(out)
        digest.append({
            "task_id": task_id,
            "summary": _truncate_text(content, 1000),
        })
    return digest[:24]


def _format_instruction(format_type: str) -> str:
    if format_type.lower() == "latex":
        return """Output the paper in LaTeX format.
Use standard LaTeX syntax with proper sectioning.
Use \\section{}, \\subsection{}, and academic writing style.
Include placeholders like \\includegraphics{filename.png} where suitable.
"""
    return """Output the paper in Markdown format.
Use markdown headers (#, ##, ###) and academic writing style.
Include placeholders like `[Figure: filename.png]` where suitable.
"""


async def _run_single_pass_llm(
    *,
    plan: dict,
    outputs: dict,
    api_config: dict,
    format_type: str,
    on_thinking: Optional[Callable[..., Any]],
    abort_event: Optional[Any],
) -> str:
    plan_fmt = _maars_plan_to_paper_format(plan)
    conclusion = _synthesize_conclusion_from_outputs(outputs or {})
    artifacts = [f"{tid}_output" for tid in (outputs or {}).keys()]

    system_instruction = """You are an academic writing assistant.
Your task is to write a comprehensive research paper based on the provided plan and task outputs.
The paper should follow a standard academic structure:
1. Title
2. Abstract
3. Introduction
4. Methodology
5. Results
6. Discussion
7. Conclusion
8. References

Prefer concrete findings from the outputs over generic filler text.
If some evidence is missing, explicitly state the limitation instead of fabricating results.

""" + _format_instruction(format_type)

    user_prompt = f"""
Experiment Title: {plan_fmt.get('title', 'Untitled')}
Goal: {plan_fmt.get('goal', 'N/A')}

Methodology Steps:
{json.dumps(plan_fmt.get('steps', []), ensure_ascii=False, indent=2)}

Conclusion & Findings:
{json.dumps(conclusion, ensure_ascii=False, indent=2)}

Task Output Digest:
{json.dumps(_build_output_digest(outputs or {}), ensure_ascii=False, indent=2)}

Available Artifacts (Figures/Tables):
{', '.join(artifacts)}

Please write the full paper.
"""

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_prompt},
    ]

    cfg = merge_phase_config(api_config, "paper")

    async def on_chunk(chunk: str):
        await _emit_thinking(on_thinking, chunk, "Paper")

    result = await chat_completion(
        messages,
        cfg,
        on_chunk=on_chunk,
        abort_event=abort_event,
        stream=True,
    )
    return result if isinstance(result, str) else str(result or "")


async def _run_agent_mvp(
    *,
    plan: dict,
    outputs: dict,
    api_config: dict,
    format_type: str,
    on_thinking: Optional[Callable[..., Any]],
    abort_event: Optional[Any],
) -> str:
    cfg = merge_phase_config(api_config, "paper")
    plan_fmt = _maars_plan_to_paper_format(plan)
    output_digest = _build_output_digest(outputs or {})

    await _emit_thinking(on_thinking, "[Paper Agent] Building paper outline...\n", "PaperPlan")

    outline_messages = [
        {
            "role": "system",
            "content": """You are a paper-planning agent.
Create a compact JSON outline for an academic paper.
Return JSON only with this schema:
{
  \"title\": string,
  \"abstract_focus\": string,
  \"sections\": [
    {\"heading\": string, \"purpose\": string, \"task_ids\": [string]}
  ]
}
Rules:
- Produce 5 to 7 sections.
- Use task_ids only from the provided digest when relevant.
- Keep headings academic and specific.
""",
        },
        {
            "role": "user",
            "content": f"""
Research Goal:
{plan_fmt.get('goal', 'N/A')}

Plan Steps:
{json.dumps(plan_fmt.get('steps', []), ensure_ascii=False, indent=2)}

Task Output Digest:
{json.dumps(output_digest, ensure_ascii=False, indent=2)}
""",
        },
    ]

    outline_raw = await chat_completion(
        outline_messages,
        cfg,
        abort_event=abort_event,
        stream=False,
        response_format={"type": "json_object"},
    )

    if not isinstance(outline_raw, str):
        outline_raw = str(outline_raw or "")
    try:
        outline = json.loads(outline_raw)
    except json.JSONDecodeError:
        logger.warning("Paper Agent outline JSON parse failed; falling back to single-pass LLM")
        return await _run_single_pass_llm(
            plan=plan,
            outputs=outputs,
            api_config=api_config,
            format_type=format_type,
            on_thinking=on_thinking,
            abort_event=abort_event,
        )

    title = str(outline.get("title") or plan_fmt.get("title") or "Untitled").strip()
    abstract_focus = str(outline.get("abstract_focus") or plan_fmt.get("goal") or "").strip()
    sections = outline.get("sections") or []
    if not isinstance(sections, list) or not sections:
        return await _run_single_pass_llm(
            plan=plan,
            outputs=outputs,
            api_config=api_config,
            format_type=format_type,
            on_thinking=on_thinking,
            abort_event=abort_event,
        )

    rendered_sections: list[str] = []
    for idx, section in enumerate(sections, start=1):
        heading = str(section.get("heading") or f"Section {idx}").strip()
        purpose = str(section.get("purpose") or "").strip()
        task_ids = [str(tid).strip() for tid in (section.get("task_ids") or []) if str(tid).strip()]
        relevant_outputs = [item for item in output_digest if item.get("task_id") in task_ids] or output_digest[:6]

        await _emit_thinking(on_thinking, f"[Paper Agent] Drafting section {idx}/{len(sections)}: {heading}\n", "PaperWrite")

        section_messages = [
            {
                "role": "system",
                "content": """You are a research-writing agent drafting one section of a paper.
Write only the requested section content.
Be evidence-grounded, concise, and academic.
Do not invent experiments or citations not supported by the inputs.
""" + _format_instruction(format_type),
            },
            {
                "role": "user",
                "content": f"""
Paper Title: {title}
Paper Goal: {plan_fmt.get('goal', 'N/A')}
Abstract Focus: {abstract_focus}
Section Heading: {heading}
Section Purpose: {purpose}
Relevant Task Outputs:
{json.dumps(relevant_outputs, ensure_ascii=False, indent=2)}

Write only this section.
""",
            },
        ]

        section_text = await chat_completion(
            section_messages,
            cfg,
            on_chunk=None,
            abort_event=abort_event,
            stream=False,
        )
        section_text = section_text if isinstance(section_text, str) else str(section_text or "")

        if format_type.lower() == "latex":
            rendered_sections.append(f"\\section{{{heading}}}\n{section_text.strip()}\n")
        else:
            rendered_sections.append(f"## {heading}\n\n{section_text.strip()}\n")

    await _emit_thinking(on_thinking, "[Paper Agent] Assembling final draft...\n", "PaperAssemble")

    if format_type.lower() == "latex":
        return (
            f"\\section*{{Abstract}}\n{abstract_focus}\n\n"
            + "\n".join(rendered_sections)
        ).strip()

    return (
        f"# {title}\n\n"
        f"> Abstract focus: {abstract_focus}\n\n"
        + "\n".join(rendered_sections)
    ).strip()


async def run_paper_agent(
    plan: dict,
    outputs: dict,
    api_config: dict,
    format_type: str = "markdown",
    on_thinking: Optional[Callable[..., Any]] = None,
    abort_event: Optional[Any] = None,
) -> str:
    """Generate paper draft in mock / llm / agent mode."""
    use_mock = api_config.get("paperUseMock", True)
    if use_mock:
        mock = _load_mock_response()
        if not mock:
            raise ValueError("No mock data for paper/_default")
        stream = on_thinking is not None

        def stream_chunk(chunk: str):
            if on_thinking and chunk:
                return on_thinking(chunk, None, "Paper", None)

        effective_on_thinking = stream_chunk if stream else None
        content = await mock_chat_completion(
            mock["content"],
            mock["reasoning"],
            effective_on_thinking,
            stream=stream,
            abort_event=abort_event,
        )
        return content or ""
    try:
        if api_config.get("paperAgentMode", False):
            logger.info("Paper Agent mode selected; running agent-style MVP pipeline")
            return await _run_agent_mvp(
                plan=plan,
                outputs=outputs,
                api_config=api_config,
                format_type=format_type,
                on_thinking=on_thinking,
                abort_event=abort_event,
            )

        return await _run_single_pass_llm(
            plan=plan,
            outputs=outputs,
            api_config=api_config,
            format_type=format_type,
            on_thinking=on_thinking,
            abort_event=abort_event,
        )
    except Exception as e:
        return f"Error generating paper: {str(e)}"
