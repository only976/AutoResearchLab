"""Database Module.

Storage is SQLite-backed (see `db/sqlite_backend.py`), including settings.
"""

import shutil

from loguru import logger

from .db_paths import (
    DB_DIR,
    DEFAULT_IDEA_ID,
    SANDBOX_DIR,
    _validate_idea_id,
    _validate_plan_id,
    ensure_execution_task_dirs,
    ensure_sandbox_dir,
    find_execution_run_ids_for_research,
    get_execution_sandbox_root,
    get_execution_src_dir,
    get_execution_step_root_dir,
    get_execution_task_src_dir,
    get_execution_task_step_dir,
    get_sandbox_dir,
)
from .db_settings import get_effective_config, get_settings, save_settings
from .db_entities import (
    get_execution,
    get_idea,
    get_plan,
    list_idea_ids,
    list_recent_plans,
    save_execution,
    save_idea,
    save_plan,
)
from .db_artifacts import (
    delete_task_artifact,
    get_task_artifact,
    list_plan_outputs,
    save_ai_response,
    save_task_artifact,
    save_validation_report,
)
from .db_research_ops import (
    clear_research_stage_data_for_retry,
    create_research,
    delete_research_cascade,
    delete_task_attempt_memories,
    get_paper,
    get_research,
    list_researches,
    list_task_attempt_memories,
    save_paper,
    save_task_attempt_memory,
    update_research_stage,
)


async def clear_db() -> dict:
    """Clear DB runtime artifacts (ideas/plans/execution/research/papers). Keeps settings."""
    from .sqlite_backend_research import clear_all_data

    removed = []
    await clear_all_data()
    if DB_DIR.exists():
        for p in DB_DIR.iterdir():
            if not p.is_dir() or p.name.startswith("."):
                continue
            try:
                shutil.rmtree(p)
                removed.append(p.name)
            except OSError as e:
                logger.warning("Failed to remove %s: %s", p, e)
    if SANDBOX_DIR.exists() and SANDBOX_DIR.is_dir():
        for p in SANDBOX_DIR.iterdir():
            if not p.is_dir() or p.name.startswith("."):
                continue
            try:
                shutil.rmtree(p)
                removed.append(f"sandbox/{p.name}")
            except OSError as e:
                logger.warning("Failed to remove %s: %s", p, e)
    return {"success": True, "removed": removed}
