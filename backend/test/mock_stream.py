"""Mock AI streaming simulation.

Simulates SSE-style reasoning chunks for frontend thinking display.

Test suite can speed this up by setting:
- MAARS_MOCK_STREAM_CHUNK_SIZE
- MAARS_MOCK_STREAM_DELAY_MS
"""

import asyncio
import os
from typing import Callable, Optional


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


async def simulate_reasoning_stream(
    reasoning: str,
    on_thinking: Callable[[str], None],
    chunk_size: Optional[int] = None,
    delay_ms: Optional[int] = None,
    abort_event: Optional[asyncio.Event] = None,
) -> None:
    """Simulate streaming reasoning content to on_thinking callback."""
    if not reasoning or not isinstance(reasoning, str):
        return
    if not callable(on_thinking):
        return

    effective_chunk_size = chunk_size or _env_int("MAARS_MOCK_STREAM_CHUNK_SIZE", 8)
    effective_delay_ms = delay_ms if delay_ms is not None else _env_int("MAARS_MOCK_STREAM_DELAY_MS", 30)
    effective_chunk_size = max(1, effective_chunk_size)
    effective_delay_s = max(0.0, effective_delay_ms / 1000.0)

    for i in range(0, len(reasoning), effective_chunk_size):
        if abort_event and abort_event.is_set():
            raise asyncio.CancelledError("Aborted")
        chunk = reasoning[i : i + effective_chunk_size]
        if chunk:
            r = on_thinking(chunk)
            if asyncio.iscoroutine(r):
                await r
        if effective_delay_s:
            await asyncio.sleep(effective_delay_s)


async def mock_chat_completion(
    content: str,
    reasoning: str,
    on_thinking: Callable[[str], None],
    chunk_size: Optional[int] = None,
    delay_ms: Optional[int] = None,
    abort_event: Optional[asyncio.Event] = None,
    stream: bool = True,
) -> str:
    """Run mock chat completion: optionally stream reasoning, then return content."""
    if stream and callable(on_thinking):
        await simulate_reasoning_stream(
            reasoning or "", on_thinking, chunk_size, delay_ms, abort_event
        )
    return content or ""
