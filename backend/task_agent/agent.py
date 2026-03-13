"""
Task Agent - Google ADK 驱动 (taskAgentMode=True)。
替代自实现 ReAct 循环，使用 backend/task_agent/adk_runner.py。
"""

from typing import Any, Callable, Dict, Optional

from . import adk_runner


async def run_task_agent(
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
    """Task Agent 入口。使用 Google ADK 驱动。"""
    return await adk_runner.run_task_agent_adk(
        task_id=task_id,
        description=description,
        input_spec=input_spec,
        output_spec=output_spec,
        resolved_inputs=resolved_inputs,
        api_config=api_config,
        abort_event=abort_event,
        on_thinking=on_thinking,
        idea_id=idea_id,
        plan_id=plan_id,
        execution_run_id=execution_run_id,
        docker_container_name=docker_container_name,
        validation_spec=validation_spec,
        idea_context=idea_context,
        execution_context=execution_context,
    )
