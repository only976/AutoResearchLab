"""
Task Agent 单轮 LLM 实现 - 任务执行与验证。
Agent 实现放在 task_agent/，单轮 LLM 放在 task_agent/llm/。
"""

from .executor import execute_task
from .validation import validate_task_output_with_llm

__all__ = ["execute_task", "validate_task_output_with_llm"]
