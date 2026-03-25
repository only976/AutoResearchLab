"""Research/paper cleanup operations extracted from sqlite_backend."""

from typing import Any

from loguru import logger

from . import sqlite_backend as base


async def create_research(research_id: str, prompt: str, title: str) -> None:
    async with base._db() as db:
        t = base._now()
        await db.execute(
            "INSERT INTO researches(research_id,prompt,title,stage,stage_status,current_idea_id,current_plan_id,created_at,updated_at,error) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (research_id, prompt, title, "refine", "idle", None, None, t, t, None),
        )
        await db.commit()


async def list_researches() -> list[dict]:
    async with base._db() as db:
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
    async with base._db() as db:
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
    params.append(base._now())
    params.append(research_id)

    sql = "UPDATE researches SET " + ", ".join(fields) + " WHERE research_id = ?"
    async with base._db() as db:
        await db.execute(sql, params)
        await db.commit()


async def clear_all_data() -> list[str]:
    """Clear all sqlite data (ideas/plans/executions/artifacts/researches)."""
    tables = [
        "ideas",
        "plans",
        "executions",
        "task_artifacts",
        "validation_reports",
        "ai_responses",
        "papers",
        "task_attempt_memories",
        "researches",
    ]
    async with base._db() as db:
        for t in tables:
            try:
                await db.execute(f"DELETE FROM {t}")
            except Exception as e:
                logger.warning("Failed to clear %s: %s", t, e)
        await db.commit()
    return tables


async def save_paper(idea_id: str, plan_id: str, *, format_type: str, content: str) -> None:
    async with base._db() as db:
        await db.execute(
            "INSERT INTO papers(idea_id, plan_id, format, content, updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(idea_id, plan_id) DO UPDATE SET format=excluded.format, content=excluded.content, updated_at=excluded.updated_at",
            (idea_id, plan_id, format_type or "markdown", content or "", base._now()),
        )
        await db.commit()


async def get_paper(idea_id: str, plan_id: str) -> dict | None:
    async with base._db() as db:
        async with db.execute(
            "SELECT format, content FROM papers WHERE idea_id=? AND plan_id=?",
            (idea_id, plan_id),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return {"format": row["format"], "content": row["content"]}


async def clear_research_stage_data_for_retry(idea_id: str | None, plan_id: str | None, stage: str) -> dict:
    """Clear data for stage retry semantics: clear current stage outputs and all downstream outputs."""
    idea = str(idea_id or "").strip()
    plan = str(plan_id or "").strip()
    s = str(stage or "").strip().lower()
    cleared: list[str] = []

    if not idea:
        return {"success": True, "cleared": cleared}

    async with base._db() as db:
        if s in ("refine", "plan"):
            if plan:
                await db.execute(
                    "DELETE FROM task_attempt_memories WHERE research_id IN (SELECT research_id FROM researches WHERE current_idea_id = ? AND current_plan_id = ?)",
                    (idea, plan),
                )
            else:
                await db.execute(
                    "DELETE FROM task_attempt_memories WHERE research_id IN (SELECT research_id FROM researches WHERE current_idea_id = ?)",
                    (idea,),
                )
            cleared.append("task_attempt_memories")

        if s == "refine":
            await db.execute("DELETE FROM ideas WHERE idea_id = ?", (idea,))
            cleared.append("ideas")
            for table in ("plans", "executions", "task_artifacts", "validation_reports", "ai_responses", "papers"):
                await db.execute(f"DELETE FROM {table} WHERE idea_id = ?", (idea,))
                cleared.append(table)

        elif s == "plan":
            if plan:
                await db.execute("DELETE FROM plans WHERE idea_id = ? AND plan_id = ?", (idea, plan))
                cleared.append("plans")
                for table in ("executions", "task_artifacts", "validation_reports", "ai_responses", "papers"):
                    await db.execute(f"DELETE FROM {table} WHERE idea_id = ? AND plan_id = ?", (idea, plan))
                    cleared.append(table)
            else:
                await db.execute("DELETE FROM plans WHERE idea_id = ?", (idea,))
                cleared.append("plans")
                for table in ("executions", "task_artifacts", "validation_reports", "ai_responses", "papers"):
                    await db.execute(f"DELETE FROM {table} WHERE idea_id = ?", (idea,))
                    cleared.append(table)

        elif s == "execute":
            if plan:
                for table in ("executions", "task_artifacts", "validation_reports", "papers"):
                    await db.execute(f"DELETE FROM {table} WHERE idea_id = ? AND plan_id = ?", (idea, plan))
                    cleared.append(table)
            else:
                for table in ("executions", "task_artifacts", "validation_reports", "papers"):
                    await db.execute(f"DELETE FROM {table} WHERE idea_id = ?", (idea,))
                    cleared.append(table)

        elif s == "paper":
            if plan:
                await db.execute("DELETE FROM papers WHERE idea_id = ? AND plan_id = ?", (idea, plan))
            else:
                await db.execute("DELETE FROM papers WHERE idea_id = ?", (idea,))
            cleared.append("papers")

        await db.commit()

    return {"success": True, "cleared": cleared}


async def delete_research_cascade(research_id: str) -> dict:
    """Delete a research and all related data (idea, plan, execution, artifacts, papers, etc.)."""
    research = await get_research(research_id)
    if not research:
        return {"success": False, "error": "Research not found"}

    idea_id = research.get("currentIdeaId")
    plan_id = research.get("currentPlanId")

    async with base._db() as db:
        await db.execute("DELETE FROM researches WHERE research_id = ?", (research_id,))
        await db.execute("DELETE FROM task_attempt_memories WHERE research_id = ?", (research_id,))

        if idea_id:
            await db.execute("DELETE FROM ideas WHERE idea_id = ?", (idea_id,))

            if plan_id:
                await db.execute("DELETE FROM plans WHERE idea_id = ? AND plan_id = ?", (idea_id, plan_id))
                await db.execute("DELETE FROM executions WHERE idea_id = ? AND plan_id = ?", (idea_id, plan_id))
                await db.execute("DELETE FROM task_artifacts WHERE idea_id = ? AND plan_id = ?", (idea_id, plan_id))
                await db.execute("DELETE FROM validation_reports WHERE idea_id = ? AND plan_id = ?", (idea_id, plan_id))
                await db.execute("DELETE FROM ai_responses WHERE idea_id = ? AND plan_id = ?", (idea_id, plan_id))
                await db.execute("DELETE FROM papers WHERE idea_id = ? AND plan_id = ?", (idea_id, plan_id))
            else:
                await db.execute("DELETE FROM plans WHERE idea_id = ?", (idea_id,))
                await db.execute("DELETE FROM executions WHERE idea_id = ?", (idea_id,))
                await db.execute("DELETE FROM task_artifacts WHERE idea_id = ?", (idea_id,))
                await db.execute("DELETE FROM validation_reports WHERE idea_id = ?", (idea_id,))
                await db.execute("DELETE FROM ai_responses WHERE idea_id = ?", (idea_id,))
                await db.execute("DELETE FROM papers WHERE idea_id = ?", (idea_id,))

        await db.commit()

    return {"success": True, "ideaId": idea_id, "planId": plan_id}
