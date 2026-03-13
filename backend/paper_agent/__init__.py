"""Paper Agent entrypoint.

Supports:
- mock mode
- single-pass llm drafting
- agent-style MVP drafting (outline -> sections -> assembly)
"""

from .runner import run_paper_agent

__all__ = ["run_paper_agent"]
