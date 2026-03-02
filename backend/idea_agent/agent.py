"""
Idea Agent - ReAct-style agent loop (ideaAgentMode=True).
Uses ExtractKeywords, SearchArxiv, FilterPapers, RefineIdea, FinishIdea, etc.
Agent 实现放在 idea_agent/，单轮 LLM 放在 idea_agent/llm/。
"""

import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from shared.constants import IDEA_AGENT_MAX_TURNS, TEMP_AGENT_LOOP
from shared.llm_client import chat_completion, merge_phase_config
from shared.utils import format_tool_args_preview

from .agent_tools import IDEA_AGENT_TOOLS, execute_idea_agent_tool

IDEA_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = IDEA_DIR / "prompts"
_prompt_cache: Dict[str, str] = {}


def _get_prompt_cached(filename: str) -> str:
    """加载 idea agent prompt 文件。"""
    if filename not in _prompt_cache:
        path = PROMPTS_DIR / filename
        _prompt_cache[filename] = path.read_text(encoding="utf-8").strip()
    return _prompt_cache[filename]


def _raise_if_aborted(abort_event: Optional[Any]) -> None:
    """Raise CancelledError if abort_event is set."""
    if abort_event and abort_event.is_set():
        raise asyncio.CancelledError("Idea Agent aborted")


async def run_idea_agent(
    idea: str,
    api_config: dict,
    limit: int = 10,
    on_thinking: Optional[Callable[..., Any]] = None,
    abort_event: Optional[Any] = None,
) -> dict:
    """
    ReAct-style Agent loop for Idea Agent.
    返回 {keywords, papers, refined_idea}，与 collect_literature 一致。
    """
    use_mock = api_config.get("ideaUseMock", True)
    if use_mock:
        return await _run_idea_agent_mock(
            idea, api_config, limit, on_thinking, abort_event
        )

    idea_state: Dict[str, Any] = {
        "idea": idea,
        "keywords": [],
        "papers": [],
        "filtered_papers": [],
        "analysis": "",
        "refined_idea": {},
    }

    system_prompt = _get_prompt_cached("idea-agent-prompt.txt")
    user_message = f"**User's fuzzy idea:** {idea}\n\nProcess the idea using the workflow. Call FinishIdea when done."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    cfg = merge_phase_config(api_config, "idea")
    max_turns = IDEA_AGENT_MAX_TURNS
    temperature = TEMP_AGENT_LOOP
    on_thinking_fn = on_thinking or (lambda *a, **_: None)

    turn = 0
    while turn < max_turns:
        turn += 1
        _raise_if_aborted(abort_event)

        result = await chat_completion(
            messages,
            cfg,
            on_chunk=None,
            abort_event=abort_event,
            stream=False,
            temperature=temperature,
            response_format=None,
            tools=IDEA_AGENT_TOOLS,
        )

        content: str = ""
        if isinstance(result, dict):
            raw_content = result.get("content") or ""
            content = raw_content if isinstance(raw_content, str) else str(raw_content)
        else:
            content = result or ""

        schedule_info = {"turn": turn, "max_turns": max_turns, "operation": "Refine"}
        if on_thinking_fn and content:
            r = on_thinking_fn(
                content, task_id=None, operation="Refine", schedule_info=schedule_info
            )
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
                sig = (
                    tc.get("thought_signature")
                    or tc.get("thoughtSignature")
                    or (sig_from_any if i == 0 else None)
                )
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
            finish_result = None
            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                args = fn.get("arguments") or "{}"
                if on_thinking_fn:
                    tool_args_raw = (args[:200] + "...") if len(args) > 200 else args
                    tool_args_preview = format_tool_args_preview(name, args)
                    tool_schedule = {
                        "turn": turn,
                        "max_turns": max_turns,
                        "tool_name": name,
                        "tool_args": tool_args_raw,
                        "tool_args_preview": tool_args_preview,
                        "operation": "Refine",
                    }
                    r = on_thinking_fn(
                        "", task_id=None, operation="Refine", schedule_info=tool_schedule
                    )
                    if asyncio.iscoroutine(r):
                        await r
                try:
                    is_finish, tool_result = await execute_idea_agent_tool(
                        name,
                        args,
                        idea_state,
                        on_thinking=on_thinking_fn,
                        abort_event=abort_event,
                        api_config=api_config,
                        limit=limit,
                    )
                except Exception as e:
                    tool_result = f"Error: {e}"
                    is_finish = False

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": tool_result,
                    }
                )

                if is_finish:
                    finished = True
                    try:
                        import orjson

                        finish_result = orjson.loads(tool_result)
                    except Exception:
                        finish_result = {}
                    break

            if finished and finish_result:
                return {
                    "keywords": finish_result.get("keywords", []),
                    "papers": finish_result.get("papers", []),
                    "refined_idea": finish_result.get("refined_idea", {}),
                }
            continue

        break

    # 未正常 Finish，回退到 idea_state
    return {
        "keywords": idea_state.get("keywords", []),
        "papers": idea_state.get("papers", []),
        "refined_idea": idea_state.get("refined_idea", {}),
    }


async def _run_idea_agent_mock(
    idea: str,
    api_config: dict,
    limit: int,
    on_thinking: Optional[Callable],
    abort_event: Optional[Any],
) -> dict:
    """Mock Agent 模式：模拟工具调用序列（ExtractKeywords → SearchArxiv → FilterPapers → RefineIdea → FinishIdea），使用 refine.json、refine-idea.json。"""
    mock_tools = [
        "ExtractKeywords",
        "SearchArxiv",
        "FilterPapers",
        "RefineIdea",
        "FinishIdea",
    ]
    on_thinking_fn = on_thinking or (lambda *a, **_: None)
    for i, tool_name in enumerate(mock_tools, start=1):
        if abort_event and abort_event.is_set():
            raise asyncio.CancelledError("Idea Agent aborted")
        tool_schedule = {
            "turn": i,
            "max_turns": len(mock_tools),
            "tool_name": tool_name,
            "tool_args": "(...)",
            "tool_args_preview": None,
            "operation": "Refine",
        }
        r = on_thinking_fn(
            "", task_id=None, operation="Refine", schedule_info=tool_schedule
        )
        if asyncio.iscoroutine(r):
            await r
        await asyncio.sleep(0.03)
    from . import collect_literature

    return await collect_literature(
        idea=idea,
        api_config=api_config,
        limit=limit,
        on_thinking=on_thinking,
        abort_event=abort_event,
    )
