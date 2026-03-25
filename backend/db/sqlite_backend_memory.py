"""Task attempt memory operations extracted from sqlite_backend."""

from . import sqlite_backend as base


async def save_task_attempt_memory(
    research_id: str,
    task_id: str,
    attempt: int,
    value: dict,
) -> dict:
    payload = base._json_dumps(value or {})
    async with base._db() as db:
        await db.execute(
            "INSERT INTO task_attempt_memories(research_id, task_id, attempt, data, updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(research_id, task_id, attempt) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (research_id, task_id, int(attempt), payload, base._now()),
        )
        await db.commit()
    return {"success": True}


async def list_task_attempt_memories(research_id: str, task_id: str | None = None) -> list[dict]:
    async with base._db() as db:
        if task_id:
            async with db.execute(
                "SELECT research_id, task_id, attempt, data, updated_at FROM task_attempt_memories WHERE research_id = ? AND task_id = ? ORDER BY attempt ASC, updated_at ASC",
                (research_id, task_id),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute(
                "SELECT research_id, task_id, attempt, data, updated_at FROM task_attempt_memories WHERE research_id = ? ORDER BY task_id ASC, attempt ASC, updated_at ASC",
                (research_id,),
            ) as cur:
                rows = await cur.fetchall()
    out: list[dict] = []
    for row in rows:
        out.append(
            {
                "researchId": row["research_id"],
                "taskId": row["task_id"],
                "attempt": int(row["attempt"]),
                "data": base._json_loads(row["data"]) or {},
                "updatedAt": row["updated_at"],
            }
        )
    return out


async def delete_task_attempt_memories(
    research_id: str,
    task_id: str | None = None,
) -> int:
    async with base._db() as db:
        if task_id:
            cur = await db.execute(
                "DELETE FROM task_attempt_memories WHERE research_id = ? AND task_id = ?",
                (research_id, task_id),
            )
        else:
            cur = await db.execute(
                "DELETE FROM task_attempt_memories WHERE research_id = ?",
                (research_id,),
            )
        await db.commit()
        return cur.rowcount or 0
