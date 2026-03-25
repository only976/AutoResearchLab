from __future__ import annotations

from . import sqlite_backend as base


async def get_settings(settings_key: str = "global") -> dict:
    async with base._db() as db:
        async with db.execute("SELECT data FROM settings WHERE settings_key = ?", (settings_key,)) as cur:
            row = await cur.fetchone()
        if not row:
            return {}
        return base._json_loads(row["data"]) or {}


async def save_settings(data: dict, settings_key: str = "global") -> dict:
    payload = base._json_dumps(data or {})
    async with base._db() as db:
        await db.execute(
            "INSERT INTO settings(settings_key, data, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(settings_key) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (settings_key, payload, base._now()),
        )
        await db.commit()
    return {"success": True}


async def get_idea(idea_id: str) -> dict | None:
    async with base._db() as db:
        async with db.execute("SELECT data FROM ideas WHERE idea_id = ?", (idea_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return base._json_loads(row["data"]) or None


async def save_idea(idea_id: str, idea_data: dict) -> dict:
    payload = base._json_dumps(idea_data or {})
    async with base._db() as db:
        await db.execute(
            "INSERT INTO ideas(idea_id, data, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(idea_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (idea_id, payload, base._now()),
        )
        await db.commit()
    return {"success": True, "idea": idea_data}


async def list_idea_ids() -> list[str]:
    async with base._db() as db:
        async with db.execute("SELECT idea_id FROM ideas ORDER BY updated_at DESC") as cur:
            rows = await cur.fetchall()
        return [r["idea_id"] for r in rows]


async def get_plan(idea_id: str, plan_id: str) -> dict | None:
    async with base._db() as db:
        async with db.execute(
            "SELECT data FROM plans WHERE idea_id = ? AND plan_id = ?",
            (idea_id, plan_id),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return base._json_loads(row["data"]) or None


async def save_plan(idea_id: str, plan_id: str, plan: dict) -> dict:
    payload = base._json_dumps(plan or {})
    async with base._db() as db:
        await db.execute(
            "INSERT INTO plans(idea_id, plan_id, data, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(idea_id, plan_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (idea_id, plan_id, payload, base._now()),
        )
        await db.commit()
    return {"success": True, "plan": plan}


async def list_plan_ids(idea_id: str) -> list[str]:
    async with base._db() as db:
        async with db.execute(
            "SELECT plan_id FROM plans WHERE idea_id = ? ORDER BY updated_at DESC",
            (idea_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [r["plan_id"] for r in rows]


async def list_recent_plans() -> list[dict]:
    async with base._db() as db:
        async with db.execute("SELECT idea_id, plan_id FROM plans ORDER BY updated_at DESC") as cur:
            rows = await cur.fetchall()
        return [{"ideaId": r["idea_id"], "planId": r["plan_id"]} for r in rows]


async def get_execution(idea_id: str, plan_id: str) -> dict | None:
    async with base._db() as db:
        async with db.execute(
            "SELECT data FROM executions WHERE idea_id = ? AND plan_id = ?",
            (idea_id, plan_id),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return base._json_loads(row["data"]) or None


async def save_execution(idea_id: str, plan_id: str, execution: dict) -> dict:
    payload = base._json_dumps(execution or {})
    async with base._db() as db:
        await db.execute(
            "INSERT INTO executions(idea_id, plan_id, data, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(idea_id, plan_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (idea_id, plan_id, payload, base._now()),
        )
        await db.commit()
    return {"success": True, "execution": execution}
