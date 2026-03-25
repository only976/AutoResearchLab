"""SQLite infrastructure: schema initialization and connection management.

All domain-level CRUD lives in sqlite_backend_*.py submodules.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Any, AsyncIterator
import weakref

import aiosqlite
import orjson

DB_DIR = Path(__file__).parent


def _get_db_path() -> Path:
    return Path(os.getenv("MAARS_DB_PATH", str(DB_DIR / "maars.sqlite3")))


DB_PATH = _get_db_path()


def _now() -> float:
    return time.time()


def _json_dumps(value: Any) -> str:
    return orjson.dumps(value, option=orjson.OPT_INDENT_2).decode("utf-8")


def _json_loads(value: str | bytes | None) -> Any:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    try:
        return orjson.loads(value)
    except Exception:
        return None


_init_locks: "weakref.WeakKeyDictionary[object, object]" = weakref.WeakKeyDictionary()


def _get_init_lock():
    import asyncio

    loop = asyncio.get_running_loop()
    lock = _init_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _init_locks[loop] = lock
    return lock


async def init_sqlite() -> None:
    """Initialize DB schema (idempotent)."""
    async with _get_init_lock():
        async with aiosqlite.connect(_get_db_path()) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS ideas (
                    idea_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS plans (
                    idea_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (idea_id, plan_id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS executions (
                    idea_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (idea_id, plan_id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS task_artifacts (
                    idea_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (idea_id, plan_id, task_id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS validation_reports (
                    idea_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (idea_id, plan_id, task_id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_responses (
                    idea_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    response_type TEXT NOT NULL,
                    data TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (idea_id, plan_id, response_type)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS papers (
                    idea_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    format TEXT NOT NULL,
                    content TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (idea_id, plan_id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS researches (
                    research_id TEXT PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    title TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    stage_status TEXT NOT NULL,
                    current_idea_id TEXT,
                    current_plan_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    error TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS task_attempt_memories (
                    research_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    data TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (research_id, task_id, attempt)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    settings_key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_plans_updated ON plans(updated_at DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ideas_updated ON ideas(updated_at DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_researches_updated ON researches(updated_at DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_attempt_memories_updated ON task_attempt_memories(research_id, updated_at DESC)"
            )
            await db.commit()


async def _connect() -> aiosqlite.Connection:
    """Deprecated: use _db() context manager instead."""
    await init_sqlite()
    db = await aiosqlite.connect(_get_db_path())
    db.row_factory = aiosqlite.Row
    return db


@asynccontextmanager
async def _db() -> AsyncIterator[aiosqlite.Connection]:
    await init_sqlite()
    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        yield db
