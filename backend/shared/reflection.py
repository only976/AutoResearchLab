"""
Agent 自迭代框架：self-evaluate → learn (生成 skill) → re-execute。
三个 Agent (idea/plan/task) 共用此模块，仅 prompt 和评估维度不同。
"""

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import json_repair
from loguru import logger

from shared.constants import (
    REFLECT_MAX_ITERATIONS,
    REFLECT_QUALITY_THRESHOLD,
    TEMP_REFLECT,
    TEMP_SKILL_GEN,
)
from shared.llm_client import chat_completion, merge_phase_config

_AGENT_DIRS = {
    "idea": Path(__file__).resolve().parent.parent / "idea_agent",
    "plan": Path(__file__).resolve().parent.parent / "plan_agent",
    "task": Path(__file__).resolve().parent.parent / "task_agent",
}

_prompt_cache: Dict[str, str] = {}


def _get_prompt(path: Path) -> str:
    key = str(path)
    if key not in _prompt_cache:
        _prompt_cache[key] = path.read_text(encoding="utf-8").strip()
    return _prompt_cache[key]


def _parse_json_from_response(text: str) -> dict:
    """从 LLM 响应中提取 JSON（支持 ```json``` 代码块和 json_repair）。"""
    cleaned = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if m:
        cleaned = m.group(1).strip()
    try:
        result = json_repair.loads(cleaned)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def _build_idea_eval_context(output: dict, context: dict) -> str:
    """构建 Idea Agent 的评估上下文。"""
    idea = context.get("idea", "")
    keywords = output.get("keywords", [])
    papers = output.get("papers", [])
    refined = output.get("refined_idea", {})
    refined_desc = refined.get("description", "") if isinstance(refined, dict) else str(refined)

    papers_summary = ""
    for p in papers[:10]:
        title = p.get("title", "") if isinstance(p, dict) else str(p)
        papers_summary += f"  - {title}\n"

    return f"""**Original idea:** {idea}

**Extracted keywords:** {', '.join(keywords) if keywords else '(none)'}

**Retrieved papers ({len(papers)} total):**
{papers_summary or '  (none)'}

**Refined idea:** {refined_desc or '(none)'}"""


def _build_plan_eval_context(output: dict, context: dict) -> str:
    """构建 Plan Agent 的评估上下文。"""
    idea = context.get("idea", "")
    tasks = output.get("tasks", [])
    lines = []
    for t in tasks:
        tid = t.get("task_id", "")
        desc = (t.get("description") or "")[:100]
        deps = ",".join(t.get("dependencies") or [])
        has_io = "Y" if (t.get("input") and t.get("output")) else "N"
        lines.append(f"  - {tid}: {desc} | deps:[{deps}] io:{has_io}")
    tasks_summary = "\n".join(lines) if lines else "  (no tasks)"
    return f"""**Idea:** {idea}

**Plan tasks ({len(tasks)} total):**
{tasks_summary}"""


def _build_task_eval_context(output: Any, context: dict) -> str:
    """构建 Task Agent 的评估上下文。"""
    task_id = context.get("task_id", "")
    description = context.get("description", "")
    output_spec = context.get("output_spec", {})

    content_str = ""
    if isinstance(output, dict):
        content = output.get("content", output)
        content_str = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    elif isinstance(output, str):
        content_str = output
    else:
        content_str = str(output)

    return f"""**Task ID:** {task_id}
**Description:** {description}
**Expected output format:** {output_spec.get('format', '')}
**Expected output description:** {output_spec.get('description', '')}

**Actual output (truncated to 6000 chars):**
```
{content_str[:6000]}
```"""


_CONTEXT_BUILDERS = {
    "idea": _build_idea_eval_context,
    "plan": _build_plan_eval_context,
    "task": _build_task_eval_context,
}


async def self_evaluate(
    agent_type: str,
    output: Any,
    context: dict,
    on_thinking: Optional[Callable] = None,
    abort_event: Optional[Any] = None,
    api_config: Optional[dict] = None,
) -> dict:
    """
    评估 Agent 输出质量。
    返回 {score, analysis, improvement_areas, skill_suggestion, dimensions}。
    """
    _raise_if_aborted(abort_event)

    prompt_path = _AGENT_DIRS[agent_type] / "prompts" / "reflect-prompt.txt"
    system_prompt = _get_prompt(prompt_path)

    builder = _CONTEXT_BUILDERS.get(agent_type)
    if not builder:
        raise ValueError(f"Unknown agent_type: {agent_type}")
    user_message = builder(output, context)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    def stream_chunk(chunk: str):
        if on_thinking and chunk:
            return on_thinking(chunk, task_id=None, operation="Reflect", schedule_info=None)

    cfg = merge_phase_config(api_config or {}, "reflect")
    content = await chat_completion(
        messages,
        cfg,
        on_chunk=stream_chunk if on_thinking else None,
        abort_event=abort_event,
        stream=on_thinking is not None,
        temperature=TEMP_REFLECT,
    )

    result = _parse_json_from_response(content if isinstance(content, str) else "")
    score = result.get("score", 0)
    if isinstance(score, (int, float)):
        score = max(0, min(100, int(score)))
    else:
        score = 0

    return {
        "score": score,
        "analysis": result.get("analysis", ""),
        "dimensions": result.get("dimensions", {}),
        "improvement_areas": result.get("improvement_areas", []),
        "skill_suggestion": result.get("skill_suggestion", {}),
    }


async def generate_skill_from_reflection(
    agent_type: str,
    evaluation: dict,
    context: dict,
    api_config: Optional[dict] = None,
    abort_event: Optional[Any] = None,
) -> Optional[str]:
    """
    根据评估结果生成 SKILL.md 内容。
    仅当 evaluation.skill_suggestion.should_create == True 时调用。
    返回 SKILL.md 的完整文本，或 None。
    """
    _raise_if_aborted(abort_event)

    suggestion = evaluation.get("skill_suggestion", {})
    if not suggestion or not suggestion.get("should_create"):
        return None

    prompt_path = Path(__file__).resolve().parent / "prompts" / "skill-generation-prompt.txt"
    system_prompt = _get_prompt(prompt_path)

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    user_message = f"""**Agent type:** {agent_type}
**Timestamp:** {timestamp}
**Evaluation score:** {evaluation.get('score', 0)}
**Analysis:** {evaluation.get('analysis', '')}

**Improvement areas:**
{json.dumps(evaluation.get('improvement_areas', []), ensure_ascii=False, indent=2)}

**Skill suggestion:**
- name: {suggestion.get('name', '')}
- description: {suggestion.get('description', '')}
- instructions: {suggestion.get('instructions', '')}

Generate the SKILL.md content."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    cfg = merge_phase_config(api_config or {}, "reflect")
    content = await chat_completion(
        messages,
        cfg,
        on_chunk=None,
        abort_event=abort_event,
        stream=False,
        temperature=TEMP_SKILL_GEN,
    )

    text = content if isinstance(content, str) else ""
    m = re.search(r"```(?:markdown)?\s*([\s\S]*?)```", text)
    if m:
        return m.group(1).strip()
    stripped = text.strip()
    if stripped.startswith("---"):
        return stripped
    return None


def save_learned_skill(agent_type: str, skill_name: str, skill_content: str) -> Path:
    """
    保存学习到的 skill 到 agent 的 skills 目录。
    返回保存路径。
    """
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "-", skill_name).strip("-")[:60]
    if not safe_name:
        safe_name = f"learned-{int(time.time())}"

    skills_dir = _AGENT_DIRS[agent_type] / "skills"
    skill_dir = skills_dir / safe_name
    if skill_dir.exists():
        safe_name = f"{safe_name}-{int(time.time() * 1000) % 100000}"
        skill_dir = skills_dir / safe_name

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(skill_content, encoding="utf-8")
    logger.info("Saved learned skill: %s -> %s", skill_name, skill_path)
    return skill_path


def _raise_if_aborted(abort_event: Optional[Any]) -> None:
    if abort_event is not None and abort_event.is_set():
        raise asyncio.CancelledError("Aborted during reflection")


async def reflection_loop(
    agent_type: str,
    run_fn: Callable,
    initial_output: Any,
    context: dict,
    on_thinking: Optional[Callable] = None,
    abort_event: Optional[Any] = None,
    api_config: Optional[dict] = None,
) -> dict:
    """
    完整的自迭代循环：evaluate → learn → re-execute → evaluate ...
    返回 {output, reflection} 其中 reflection 包含评估结果和 skill 信息。

    参数:
        agent_type: "idea" | "plan" | "task"
        run_fn: 重新执行的 async callable，签名由各 agent 适配
        initial_output: Agent 首次执行的输出
        context: 评估上下文（idea、task_id 等）
        on_thinking: thinking 回调
        abort_event: 中止事件
        api_config: 含 reflectionEnabled/reflectionMaxIterations/reflectionQualityThreshold
    """
    cfg = api_config or {}
    enabled = cfg.get("reflectionEnabled", False)
    max_iterations = cfg.get("reflectionMaxIterations", REFLECT_MAX_ITERATIONS)
    threshold = cfg.get("reflectionQualityThreshold", REFLECT_QUALITY_THRESHOLD)

    if not enabled:
        return {"output": initial_output, "reflection": None}

    use_mock = cfg.get(f"{agent_type}UseMock", False)
    if use_mock:
        return {"output": initial_output, "reflection": None}

    best_output = initial_output
    best_score = 0
    skills_created = []
    all_evaluations = []

    current_output = initial_output
    for iteration in range(max_iterations + 1):
        _raise_if_aborted(abort_event)

        if on_thinking:
            separator = f"\n\n---\n**Self-Reflection (iteration {iteration + 1}/{max_iterations + 1})**\n\n"
            r = on_thinking(separator, task_id=None, operation="Reflect", schedule_info={
                "turn": iteration + 1,
                "max_turns": max_iterations + 1,
                "operation": "Reflect",
            })
            if asyncio.iscoroutine(r):
                await r

        try:
            evaluation = await self_evaluate(
                agent_type, current_output, context,
                on_thinking=on_thinking, abort_event=abort_event, api_config=api_config,
            )
        except Exception as e:
            logger.warning("Self-evaluation failed for %s (iteration %d): %s", agent_type, iteration, e)
            break

        all_evaluations.append(evaluation)
        score = evaluation.get("score", 0)

        if score > best_score:
            best_score = score
            best_output = current_output

        if score >= threshold:
            logger.info("%s reflection: score %d >= threshold %d, accepting output", agent_type, score, threshold)
            suggestion = evaluation.get("skill_suggestion", {})
            if suggestion.get("should_create") and suggestion.get("name"):
                try:
                    skill_content = await generate_skill_from_reflection(
                        agent_type, evaluation, context,
                        api_config=api_config, abort_event=abort_event,
                    )
                    if skill_content:
                        path = save_learned_skill(agent_type, suggestion["name"], skill_content)
                        skills_created.append({"name": suggestion["name"], "path": str(path)})
                except Exception as e:
                    logger.warning("Skill generation failed: %s", e)
            break

        if iteration >= max_iterations:
            logger.info("%s reflection: max iterations reached, returning best (score=%d)", agent_type, best_score)
            break

        suggestion = evaluation.get("skill_suggestion", {})
        if suggestion.get("should_create") and suggestion.get("name"):
            try:
                _raise_if_aborted(abort_event)
                skill_content = await generate_skill_from_reflection(
                    agent_type, evaluation, context,
                    api_config=api_config, abort_event=abort_event,
                )
                if skill_content:
                    path = save_learned_skill(agent_type, suggestion["name"], skill_content)
                    skills_created.append({"name": suggestion["name"], "path": str(path)})
                    if on_thinking:
                        msg = f"\n\n> Learned skill: **{suggestion['name']}** saved for future use.\n\n"
                        r = on_thinking(msg, task_id=None, operation="Reflect", schedule_info=None)
                        if asyncio.iscoroutine(r):
                            await r
            except Exception as e:
                logger.warning("Skill generation failed: %s", e)

        if on_thinking:
            msg = f"\n\n> Score {score} < threshold {threshold}. Re-executing with improved context...\n\n"
            r = on_thinking(msg, task_id=None, operation="Reflect", schedule_info=None)
            if asyncio.iscoroutine(r):
                await r

        try:
            _raise_if_aborted(abort_event)
            current_output = await run_fn()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Re-execution failed for %s: %s", agent_type, e)
            break

    return {
        "output": best_output,
        "reflection": {
            "iterations": len(all_evaluations),
            "best_score": best_score,
            "evaluations": all_evaluations,
            "skills_created": skills_created,
        },
    }
