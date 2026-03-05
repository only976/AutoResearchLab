from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Iterable

import orjson
from loguru import logger


_backend_sink_id: int | None = None
_frontend_lock = threading.Lock()


def get_logs_dir() -> Path:
    env = os.getenv("MAARS_LOGS_DIR")
    if env:
        return Path(env).expanduser().resolve()
    # shared/ -> backend/ -> repo root
    return Path(__file__).resolve().parents[2] / "logs"


def configure_backend_file_logging() -> None:
    """Add a Loguru file sink for backend logs (idempotent)."""
    global _backend_sink_id
    if _backend_sink_id is not None:
        return

    logs_dir = get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "backend.log"

    _backend_sink_id = logger.add(
        str(log_path),
        level=os.getenv("MAARS_BACKEND_LOG_LEVEL", "INFO"),
        enqueue=True,
        backtrace=False,
        diagnose=False,
        rotation=os.getenv("MAARS_BACKEND_LOG_ROTATION", "10 MB"),
        retention=os.getenv("MAARS_BACKEND_LOG_RETENTION", "7 days"),
    )


def append_frontend_log_records(records: Iterable[dict[str, Any]]) -> None:
    logs_dir = get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / "frontend.log"

    with _frontend_lock:
        with path.open("ab") as f:
            for r in records:
                try:
                    f.write(orjson.dumps(r))
                    f.write(b"\n")
                except Exception:
                    # Best-effort logging only; ignore malformed record.
                    continue


def build_frontend_log_record(
    *,
    session_id: str | None,
    level: str,
    message: str,
    url: str | None = None,
    ts: float | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ts": float(ts if ts is not None else time.time()),
        "sessionId": session_id,
        "level": (level or "info"),
        "message": message,
        "url": url,
        "context": context or {},
    }
