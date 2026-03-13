"""
Live agent skill usage verifier.
Runs the real task agent ADK loop and tracks which skills it loads via LoadSkill tool calls.
"""
import json
from typing import Any, Dict, List, Tuple

from task_agent.adk_runner import run_task_agent_adk


async def verify_skill_usage(
    task_id: str,
    description: str,
    expected_skill: str,
    api_config: Dict[str, Any],
) -> Tuple[List[str], str]:
    """
    Run the task agent against a scenario and track loaded skills.
    Returns (list_of_loaded_skill_names, final_output_string).
    """
    loaded_skills: List[str] = []

    def on_thinking(text: str = "", **kwargs: Any) -> None:
        si = kwargs.get("schedule_info") or {}
        if si.get("tool_name") == "LoadSkill":
            raw_args = si.get("tool_args") or {}
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except Exception:
                    pass
            name = raw_args.get("name", "") if isinstance(raw_args, dict) else ""
            if name:
                loaded_skills.append(name)

    result = await run_task_agent_adk(
        task_id=task_id,
        description=description,
        input_spec={"description": "No specific inputs", "format": ""},
        output_spec={"description": "Produce exactly what the user asks", "format": "Markdown"},
        resolved_inputs={},
        api_config=api_config,
        abort_event=None,
        on_thinking=on_thinking,
        idea_id="test_idea",
        plan_id="test_plan",
        execution_run_id="test_exec",
        docker_container_name="",
    )

    return loaded_skills, str(result)
