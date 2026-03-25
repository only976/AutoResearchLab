"""Settings persistence and effective-config resolution helpers."""

from __future__ import annotations

import orjson
from loguru import logger

from .db_paths import DB_DIR
from .sqlite_backend_entities import (
    get_settings as _sb_get_settings,
    save_settings as _sb_save_settings,
)

SETTINGS_FILE = "settings.json"
_SETTINGS_KEY = "global"


def _resolve_config(raw: dict) -> dict:
    """
    Parse persisted settings into runtime cfg.
    Structure: preset (API connection) + agentMode (mode flags).
    """
    if not raw:
        return {}
    agent_mode = raw.get("agentMode") or {}
    idea_m = agent_mode.get("ideaAgent") or "mock"
    plan_m = agent_mode.get("planAgent") or "mock"
    task_m = agent_mode.get("taskAgent") or "mock"
    paper_m = agent_mode.get("paperAgent") or "mock"

    presets = raw.get("presets")
    current = raw.get("current")
    if isinstance(presets, dict) and current and current in presets:
        cfg = dict(presets[current])
        cfg.pop("label", None)
        cfg.pop("phases", None)
    else:
        cfg = {}

    cfg["ideaUseMock"] = idea_m == "mock"
    cfg["planUseMock"] = plan_m == "mock"
    cfg["taskUseMock"] = task_m == "mock"
    cfg["paperUseMock"] = paper_m == "mock"
    cfg["ideaAgentMode"] = idea_m == "agent"
    cfg["planAgentMode"] = plan_m == "agent"
    cfg["taskAgentMode"] = task_m == "agent"
    cfg["paperAgentMode"] = paper_m == "agent"
    source = str(agent_mode.get("literatureSource") or "").strip().lower()
    cfg["literatureSource"] = source if source in ("openalex", "arxiv") else "openalex"

    return cfg


async def get_settings() -> dict:
    """Get full settings from SQLite. One-time legacy import from settings.json if needed."""
    settings = await _sb_get_settings(_SETTINGS_KEY)
    if settings:
        return settings

    legacy_file = DB_DIR / SETTINGS_FILE
    if not legacy_file.exists():
        return {}
    try:
        data = orjson.loads(legacy_file.read_bytes())
        if isinstance(data, dict) and data:
            await _sb_save_settings(data, _SETTINGS_KEY)
            return data
    except Exception as e:
        logger.warning("Failed legacy settings import from %s: %s", legacy_file, e)
    return {}


async def get_effective_config() -> dict:
    """Get effective config for LLM/plan/execution (resolves current preset from settings)."""
    raw = await get_settings()
    return _resolve_config(raw)


async def save_settings(settings: dict) -> dict:
    """Save settings to SQLite."""
    return await _sb_save_settings(settings or {}, _SETTINGS_KEY)
