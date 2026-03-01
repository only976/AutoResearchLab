"""
Plan Agent - ReAct-style agent loop (planAgentMode=True).
Uses CheckAtomicity, Decompose, FormatTask, etc. via PLAN_AGENT_TOOLS.
Multi Agent: Plan Agent (plan_agent) + Task Agent (task_agent).
Agent 实现放在 plan_agent/，单轮 LLM 放在 plan_agent/llm/。
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional

from shared.llm_client import chat_completion as real_chat_completion, merge_phase_config

from .agent_tools import PLAN_AGENT_TOOLS, execute_plan_agent_tool
from .llm.executor import (
    MAX_PLAN_AGENT_TURNS,
    _get_prompt_cached,
    check_atomicity,
    decompose_task,
    format_task,
    raise_if_aborted,
)


def _get_plan_agent_params(api_config: Dict[str, Any]) -> tuple:
    """Return (max_turns, temperature) for Plan Agent from modeConfig or defaults."""
    mode_cfg = api_config.get("modeConfig") or {}
    agent_cfg = mode_cfg.get("agent") or {}
    llm_cfg = mode_cfg.get("llm") or {}
    max_turns = agent_cfg.get("planAgentMaxTurns") or MAX_PLAN_AGENT_TURNS
    max_turns = int(max_turns)
    temperature = (
        agent_cfg.get("planLlmTemperature")
        or llm_cfg.get("planLlmTemperature")
        or 0.3
    )
    return max_turns, float(temperature)


async def run_plan_agent(
    plan: Dict,
    on_thinking: Callable[[str], None],
    abort_event: Optional[Any],
    on_tasks_batch: Optional[Callable[[List[Dict], Dict, List[Dict]], None]],
    use_mock: bool,
    api_config: Optional[Dict],
    plan_id: Optional[str],
) -> Dict:
    """ReAct-style Agent loop for Plan Agent. Uses CheckAtomicity, Decompose, FormatTask, AddTasks, UpdateTask, GetPlan, GetNextTask, FinishPlan."""
    tasks = plan.get("tasks") or []
    root_task = next((t for t in tasks if t.get("task_id") == "0"), None)
    if not root_task:
        root_task = next(
            (t for t in tasks if t.get("task_id") and not (t.get("dependencies") or [])),
            tasks[0] if tasks else None,
        )
    if not root_task:
        raise ValueError("No decomposable task found. Generate plan first.")

    all_tasks = list(tasks)
    idea = plan.get("idea") or root_task.get("description") or ""
    plan_state: Dict[str, Any] = {
        "all_tasks": all_tasks,
        "pending_queue": ["0"],
        "idea": idea,
    }

    system_prompt = _get_prompt_cached("plan-agent-prompt.txt")
    user_message = f"**Idea:** {idea}\n\n**Root task:** task_id \"0\", description \"{root_task.get('description', '')}\"\n\nProcess all tasks until GetNextTask returns null, then call FinishPlan."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    cfg = merge_phase_config(api_config, "atomicity")
    max_turns, temperature = _get_plan_agent_params(api_config or {})
    on_thinking_fn = on_thinking or (lambda *a, **_: None)

    turn = 0
    while turn < max_turns:
        turn += 1
        raise_if_aborted(abort_event)
        if on_thinking_fn:
            r = on_thinking_fn("", task_id=None, operation="Plan", schedule_info={"turn": turn, "max_turns": max_turns})
            if asyncio.iscoroutine(r):
                await r

        result = await real_chat_completion(
            messages,
            cfg,
            on_chunk=None,
            abort_event=abort_event,
            stream=False,
            temperature=temperature,
            response_format=None,
            tools=PLAN_AGENT_TOOLS,
        )

        content: str = ""
        if isinstance(result, dict):
            raw_content = result.get("content") or ""
            content = raw_content if isinstance(raw_content, str) else str(raw_content)
        else:
            content = result or ""

        schedule_info = {"turn": turn, "max_turns": max_turns}
        if on_thinking_fn and content:
            r = on_thinking_fn(content, task_id=None, operation="Plan", schedule_info=schedule_info)
            if asyncio.iscoroutine(r):
                await r

        if isinstance(result, dict) and result.get("finish_reason") == "tool_calls":
            tool_calls = result.get("tool_calls") or []
            if not tool_calls:
                continue

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

            finished = False
            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                args = fn.get("arguments") or "{}"
                if on_thinking_fn:
                    tool_schedule = {"turn": turn, "max_turns": max_turns, "tool_name": name, "tool_args": (args[:200] + "...") if len(args) > 200 else args}
                    r = on_thinking_fn("", task_id=None, operation="Plan", schedule_info=tool_schedule)
                    if asyncio.iscoroutine(r):
                        await r
                try:
                    is_finish, tool_result = await execute_plan_agent_tool(
                        name,
                        args,
                        plan_state,
                        check_atomicity_fn=check_atomicity,
                        decompose_fn=decompose_task,
                        format_fn=format_task,
                        on_thinking=on_thinking_fn,
                        on_tasks_batch=on_tasks_batch,
                        abort_event=abort_event,
                        use_mock=use_mock,
                        api_config=api_config,
                        plan_id=plan_id,
                    )
                except Exception as e:
                    tool_result = f"Error: {e}"
                    is_finish = False

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": tool_result,
                })

                if is_finish:
                    finished = True
                    break

            if finished:
                break
            continue

        break

    plan["tasks"] = plan_state["all_tasks"]
    return {"tasks": plan_state["all_tasks"]}
