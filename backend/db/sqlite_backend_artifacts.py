from __future__ import annotations

from typing import Any

from . import sqlite_backend as base


async def get_task_artifact(idea_id: str, plan_id: str, task_id: str) -> dict | None:
    async with base._db() as db:
        async with db.execute(
            "SELECT data FROM task_artifacts WHERE idea_id=? AND plan_id=? AND task_id=?",
            (idea_id, plan_id, task_id),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return base._json_loads(row["data"]) or None


async def list_plan_outputs(idea_id: str, plan_id: str) -> dict:
    async with base._db() as db:
        async with db.execute(
            "SELECT task_id, data FROM task_artifacts WHERE idea_id=? AND plan_id=?",
            (idea_id, plan_id),
        ) as cur:
            rows = await cur.fetchall()
        result: dict[str, Any] = {}
        for r in rows:
            obj = base._json_loads(r["data"])
            if obj is not None:
                result[r["task_id"]] = obj
        return result


async def save_task_artifact(idea_id: str, plan_id: str, task_id: str, value: Any) -> dict:
    if isinstance(value, str):
        value = {"content": value}
    payload = base._json_dumps(value or {})
    async with base._db() as db:
        await db.execute(
            "INSERT INTO task_artifacts(idea_id, plan_id, task_id, data, updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(idea_id, plan_id, task_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (idea_id, plan_id, task_id, payload, base._now()),
        )
        await db.commit()
    return {"success": True}


async def delete_task_artifact(idea_id: str, plan_id: str, task_id: str) -> bool:
    async with base._db() as db:
        cur = await db.execute(
            "DELETE FROM task_artifacts WHERE idea_id=? AND plan_id=? AND task_id=?",
            (idea_id, plan_id, task_id),
        )
        await db.commit()
        return (cur.rowcount or 0) > 0


async def save_validation_report(idea_id: str, plan_id: str, task_id: str, report: dict) -> dict:
    payload = base._json_dumps(report or {})
    async with base._db() as db:
        await db.execute(
            "INSERT INTO validation_reports(idea_id, plan_id, task_id, data, updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(idea_id, plan_id, task_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (idea_id, plan_id, task_id, payload, base._now()),
        )
        await db.commit()
    return {"success": True}


async def get_ai_responses(idea_id: str, plan_id: str, response_type: str) -> dict:
    if response_type not in ("atomicity", "decompose", "format"):
        return {}
    async with base._db() as db:
        async with db.execute(
            "SELECT data FROM ai_responses WHERE idea_id=? AND plan_id=? AND response_type=?",
            (idea_id, plan_id, response_type),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return {}
        return base._json_loads(row["data"]) or {}


async def save_ai_responses_blob(idea_id: str, plan_id: str, response_type: str, data: dict) -> None:
    if response_type not in ("atomicity", "decompose", "format"):
        return
    payload = base._json_dumps(data or {})
    async with base._db() as db:
        await db.execute(
            "INSERT INTO ai_responses(idea_id, plan_id, response_type, data, updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(idea_id, plan_id, response_type) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (idea_id, plan_id, response_type, payload, base._now()),
        )
        await db.commit()
