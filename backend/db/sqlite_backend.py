"""SQLite-backed storage implementation for MAARS.

This module intentionally stores JSON blobs (idea/plan/execution/artifacts) as TEXT.
It is designed to replace the previous file-based DB implementation.

Settings remain file-based in db/settings.json.
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
from loguru import logger

DB_DIR = Path(__file__).parent


def _get_db_path() -> Path:
    return Path(os.getenv("MAARS_DB_PATH", str(DB_DIR / "maars.sqlite3")))


# Backward-compat: some code may import DB_PATH directly.
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
                "CREATE INDEX IF NOT EXISTS idx_plans_updated ON plans(updated_at DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ideas_updated ON ideas(updated_at DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_researches_updated ON researches(updated_at DESC)"
            )
            await db.commit()


async def _connect() -> aiosqlite.Connection:
    # Deprecated: kept for compatibility with any out-of-tree imports.
    # Use `_db()` instead.
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


# --- idea ---


async def get_idea(idea_id: str) -> dict | None:
    async with _db() as db:
        async with db.execute("SELECT data FROM ideas WHERE idea_id = ?", (idea_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return _json_loads(row["data"]) or None


async def save_idea(idea_id: str, idea_data: dict) -> dict:
    payload = _json_dumps(idea_data or {})
    async with _db() as db:
        await db.execute(
            "INSERT INTO ideas(idea_id, data, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(idea_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (idea_id, payload, _now()),
        )
        await db.commit()
    return {"success": True, "idea": idea_data}


async def list_idea_ids() -> list[str]:
    async with _db() as db:
        async with db.execute("SELECT idea_id FROM ideas ORDER BY updated_at DESC") as cur:
            rows = await cur.fetchall()
        return [r["idea_id"] for r in rows]


# --- plan ---


async def get_plan(idea_id: str, plan_id: str) -> dict | None:
    async with _db() as db:
        async with db.execute(
            "SELECT data FROM plans WHERE idea_id = ? AND plan_id = ?",
            (idea_id, plan_id),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return _json_loads(row["data"]) or None


async def save_plan(idea_id: str, plan_id: str, plan: dict) -> dict:
    payload = _json_dumps(plan or {})
    async with _db() as db:
        await db.execute(
            "INSERT INTO plans(idea_id, plan_id, data, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(idea_id, plan_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (idea_id, plan_id, payload, _now()),
        )
        await db.commit()
    return {"success": True, "plan": plan}


async def list_plan_ids(idea_id: str) -> list[str]:
    async with _db() as db:
        async with db.execute(
            "SELECT plan_id FROM plans WHERE idea_id = ? ORDER BY updated_at DESC",
            (idea_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [r["plan_id"] for r in rows]


async def list_recent_plans() -> list[dict]:
    async with _db() as db:
        async with db.execute("SELECT idea_id, plan_id FROM plans ORDER BY updated_at DESC") as cur:
            rows = await cur.fetchall()
        return [{"ideaId": r["idea_id"], "planId": r["plan_id"]} for r in rows]


# --- execution ---


async def get_execution(idea_id: str, plan_id: str) -> dict | None:
    async with _db() as db:
        async with db.execute(
            "SELECT data FROM executions WHERE idea_id = ? AND plan_id = ?",
            (idea_id, plan_id),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return _json_loads(row["data"]) or None


async def save_execution(idea_id: str, plan_id: str, execution: dict) -> dict:
    payload = _json_dumps(execution or {})
    async with _db() as db:
        await db.execute(
            "INSERT INTO executions(idea_id, plan_id, data, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(idea_id, plan_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (idea_id, plan_id, payload, _now()),
        )
        await db.commit()
    return {"success": True, "execution": execution}


# --- task artifacts / validation ---


async def get_task_artifact(idea_id: str, plan_id: str, task_id: str) -> dict | None:
    async with _db() as db:
        async with db.execute(
            "SELECT data FROM task_artifacts WHERE idea_id=? AND plan_id=? AND task_id=?",
            (idea_id, plan_id, task_id),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return _json_loads(row["data"]) or None


async def list_plan_outputs(idea_id: str, plan_id: str) -> dict:
    async with _db() as db:
        async with db.execute(
            "SELECT task_id, data FROM task_artifacts WHERE idea_id=? AND plan_id=?",
            (idea_id, plan_id),
        ) as cur:
            rows = await cur.fetchall()
        result: dict[str, Any] = {}
        for r in rows:
            obj = _json_loads(r["data"])
            if obj is not None:
                result[r["task_id"]] = obj
        return result


async def save_task_artifact(idea_id: str, plan_id: str, task_id: str, value: Any) -> dict:
    if isinstance(value, str):
        value = {"content": value}
    payload = _json_dumps(value or {})
    async with _db() as db:
        await db.execute(
            "INSERT INTO task_artifacts(idea_id, plan_id, task_id, data, updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(idea_id, plan_id, task_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (idea_id, plan_id, task_id, payload, _now()),
        )
        await db.commit()
    return {"success": True}


async def delete_task_artifact(idea_id: str, plan_id: str, task_id: str) -> bool:
    async with _db() as db:
        cur = await db.execute(
            "DELETE FROM task_artifacts WHERE idea_id=? AND plan_id=? AND task_id=?",
            (idea_id, plan_id, task_id),
        )
        await db.commit()
        return (cur.rowcount or 0) > 0


async def save_validation_report(idea_id: str, plan_id: str, task_id: str, report: dict) -> dict:
    payload = _json_dumps(report or {})
    async with _db() as db:
        await db.execute(
            "INSERT INTO validation_reports(idea_id, plan_id, task_id, data, updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(idea_id, plan_id, task_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (idea_id, plan_id, task_id, payload, _now()),
        )
        await db.commit()
    return {"success": True}


# --- AI responses ---


async def get_ai_responses(idea_id: str, plan_id: str, response_type: str) -> dict:
    if response_type not in ("atomicity", "decompose", "format"):
        return {}
    async with _db() as db:
        async with db.execute(
            "SELECT data FROM ai_responses WHERE idea_id=? AND plan_id=? AND response_type=?",
            (idea_id, plan_id, response_type),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return {}
        return _json_loads(row["data"]) or {}


async def save_ai_responses_blob(idea_id: str, plan_id: str, response_type: str, data: dict) -> None:
    if response_type not in ("atomicity", "decompose", "format"):
        return
    payload = _json_dumps(data or {})
    async with _db() as db:
        await db.execute(
            "INSERT INTO ai_responses(idea_id, plan_id, response_type, data, updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(idea_id, plan_id, response_type) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (idea_id, plan_id, response_type, payload, _now()),
        )
        await db.commit()


# --- Researches ---


async def create_research(research_id: str, prompt: str, title: str) -> None:
    async with _db() as db:
        t = _now()
        await db.execute(
            "INSERT INTO researches(research_id,prompt,title,stage,stage_status,current_idea_id,current_plan_id,created_at,updated_at,error) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (research_id, prompt, title, "refine", "idle", None, None, t, t, None),
        )
        await db.commit()


async def list_researches() -> list[dict]:
    async with _db() as db:
        async with db.execute(
            "SELECT research_id, title, stage, stage_status, updated_at FROM researches ORDER BY updated_at DESC"
        ) as cur:
            rows = await cur.fetchall()
        return [
            {
                "researchId": r["research_id"],
                "title": r["title"],
                "stage": r["stage"],
                "stageStatus": r["stage_status"],
                "updatedAt": r["updated_at"],
            }
            for r in rows
        ]


async def get_research(research_id: str) -> dict | None:
    async with _db() as db:
        async with db.execute(
            "SELECT * FROM researches WHERE research_id=?",
            (research_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return {
            "researchId": row["research_id"],
            "prompt": row["prompt"],
            "title": row["title"],
            "stage": row["stage"],
            "stageStatus": row["stage_status"],
            "currentIdeaId": row["current_idea_id"],
            "currentPlanId": row["current_plan_id"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "error": row["error"],
        }


async def update_research_stage(
    research_id: str,
    *,
    stage: str | None = None,
    stage_status: str | None = None,
    current_idea_id: str | None = None,
    current_plan_id: str | None = None,
    error: str | None = None,
) -> None:
    fields = []
    params: list[Any] = []
    if stage is not None:
        fields.append("stage = ?")
        params.append(stage)
    if stage_status is not None:
        fields.append("stage_status = ?")
        params.append(stage_status)
    if current_idea_id is not None:
        fields.append("current_idea_id = ?")
        params.append(current_idea_id)
    if current_plan_id is not None:
        fields.append("current_plan_id = ?")
        params.append(current_plan_id)
    if error is not None:
        fields.append("error = ?")
        params.append(error)
    fields.append("updated_at = ?")
    params.append(_now())
    params.append(research_id)

    sql = "UPDATE researches SET " + ", ".join(fields) + " WHERE research_id = ?"
    async with _db() as db:
        await db.execute(sql, params)
        await db.commit()


async def clear_all_data() -> list[str]:
    """Clear all sqlite data (ideas/plans/executions/artifacts/researches). Returns list of table names cleared."""
    tables = [
        "ideas",
        "plans",
        "executions",
        "task_artifacts",
        "validation_reports",
        "ai_responses",
        "papers",
        "researches",
    ]
    async with _db() as db:
        for t in tables:
            try:
                await db.execute(f"DELETE FROM {t}")
            except Exception as e:
                logger.warning("Failed to clear %s: %s", t, e)
        await db.commit()
    return tables


# --- Paper ---


async def save_paper(idea_id: str, plan_id: str, *, format_type: str, content: str) -> None:
    async with _db() as db:
        await db.execute(
            "INSERT INTO papers(idea_id, plan_id, format, content, updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(idea_id, plan_id) DO UPDATE SET format=excluded.format, content=excluded.content, updated_at=excluded.updated_at",
            (idea_id, plan_id, format_type or "markdown", content or "", _now()),
        )
        await db.commit()


async def get_paper(idea_id: str, plan_id: str) -> dict | None:
    async with _db() as db:
        async with db.execute(
            "SELECT format, content FROM papers WHERE idea_id=? AND plan_id=?",
            (idea_id, plan_id),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return {"format": row["format"], "content": row["content"]}
