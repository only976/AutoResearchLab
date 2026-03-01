"""
Task Agent - 任务执行与验证（Agent 实现）。
单轮 LLM 放在 task_agent/llm/。
Validation is a fixed step after execution; workers handle both.
"""

from .pools import worker_manager
from .runner import ExecutionRunner

__all__ = [
    "ExecutionRunner",
    "worker_manager",
]
