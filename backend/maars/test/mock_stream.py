"""
Mock AI streaming simulation
Simulates SSE-style reasoning chunks for frontend Plan Agent thinking display.
Used by Plan Agent (mock-only mode).
"""

import asyncio
from typing import Callable, Optional


async def simulate_reasoning_stream(
    reasoning: str,
    on_thinking: Callable[[str], None],
    chunk_size: int = 8,
    delay_ms: int = 30,
    abort_event: Optional[asyncio.Event] = None,
) -> None:
    """Simulate streaming reasoning content to on_thinking callback."""
    if not reasoning or not isinstance(reasoning, str):
        return
    if not callable(on_thinking):
        return

    for i in range(0, len(reasoning), chunk_size):
        if abort_event and abort_event.is_set():
            raise asyncio.CancelledError("Aborted")
        chunk = reasoning[i : i + chunk_size]
        if chunk:
            on_thinking(chunk)
        await asyncio.sleep(delay_ms / 1000.0)


async def mock_chat_completion(
    content: str,
    reasoning: str,
    on_thinking: Callable[[str], None],
    chunk_size: int = 8,
    delay_ms: int = 30,
    abort_event: Optional[asyncio.Event] = None,
    stream: bool = True,
) -> str:
    """Run mock chat completion: optionally stream reasoning, then return content."""
    if stream and callable(on_thinking):
        await simulate_reasoning_stream(
            reasoning or "", on_thinking, chunk_size, delay_ms, abort_event
        )
    return content or ""
