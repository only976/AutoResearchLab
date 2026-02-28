"""
Database Module
File-based storage: db/{plan_id}/ contains plan.json, execution.json, {task_id}/output.json.
Plan generates a new plan_id folder on each new plan; all reads/writes use plan_id.
Uses orjson for faster JSON parsing.
"""

import asyncio
import re
import shutil
from pathlib import Path

import aiofiles
import json_repair
import orjson
from loguru import logger

DB_DIR = Path(__file__).parent
DEFAULT_PLAN_ID = "test"
SETTINGS_FILE = "settings.json"


def _validate_plan_id(plan_id: str) -> None:
    """Reject path traversal and invalid plan_id."""
    if not plan_id or not isinstance(plan_id, str):
        raise ValueError("plan_id must be a non-empty string")
    if ".." in plan_id or "/" in plan_id or "\\" in plan_id:
        raise ValueError("plan_id must not contain path separators")


def _validate_task_id(task_id: str) -> None:
    """Reject path traversal and invalid task_id. Only alphanumeric and underscore."""
    if not task_id or not isinstance(task_id, str):
        raise ValueError("task_id must be a non-empty string")
    if ".." in task_id or "/" in task_id or "\\" in task_id:
        raise ValueError("task_id must not contain path separators")
    if not re.match(r"^[a-zA-Z0-9_]+$", task_id):
        raise ValueError("task_id must contain only letters, digits, and underscores")


def _get_plan_dir(plan_id: str = DEFAULT_PLAN_ID) -> Path:
    return DB_DIR / plan_id


def _get_file_path(plan_id: str, filename: str) -> Path:
    return _get_plan_dir(plan_id) / filename


def _get_task_dir(plan_id: str, task_id: str) -> Path:
    """Return db/{plan_id}/{task_id}/."""
    _validate_plan_id(plan_id)
    _validate_task_id(task_id)
    return _get_plan_dir(plan_id) / task_id


def get_sandbox_dir(plan_id: str, task_id: str) -> Path:
    """Return db/{plan_id}/{task_id}/sandbox/ for isolated task execution."""
    return _get_task_dir(plan_id, task_id) / "sandbox"


async def ensure_sandbox_dir(plan_id: str, task_id: str) -> Path:
    """Create sandbox dir if not exists. Returns the sandbox path."""
    sandbox = get_sandbox_dir(plan_id, task_id)
    sandbox.mkdir(parents=True, exist_ok=True)
    return sandbox


async def get_task_artifact(plan_id: str, task_id: str):
    """Read artifact from db/{plan_id}/{task_id}/output.json. Returns dict or None."""
    _validate_plan_id(plan_id)
    _validate_task_id(task_id)
    task_dir = _get_task_dir(plan_id, task_id)
    file_path = task_dir / "output.json"
    try:
        async with aiofiles.open(file_path, "rb") as f:
            data = await f.read()
            return orjson.loads(data)
    except FileNotFoundError:
        return None
    except orjson.JSONDecodeError as e:
        logger.warning("Invalid JSON in %s: %s", file_path, e)
        return None


async def list_plan_outputs(plan_id: str) -> dict:
    """Load all task outputs for a plan. Returns {task_id: output_dict}."""
    _validate_plan_id(plan_id)
    plan_dir = _get_plan_dir(plan_id)
    if not plan_dir.exists():
        return {}
    result = {}
    for p in plan_dir.iterdir():
        if not p.is_dir() or p.name.startswith("."):
            continue
        try:
            artifact = await get_task_artifact(plan_id, p.name)
            if artifact is not None:
                result[p.name] = artifact
        except ValueError:
            continue
    return result


async def save_task_artifact(plan_id: str, task_id: str, value) -> dict:
    """Write artifact to db/{plan_id}/{task_id}/output.json. Atomic write. Accepts dict or str (wrapped as {"content": ...})."""
    _validate_plan_id(plan_id)
    _validate_task_id(task_id)
    if isinstance(value, str):
        value = {"content": value}
    task_dir = _get_task_dir(plan_id, task_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    file_path = task_dir / "output.json"
    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    content = orjson.dumps(value, option=orjson.OPT_INDENT_2).decode("utf-8")
    async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
        await f.write(content)
    tmp_path.replace(file_path)
    return {"success": True}


async def delete_task_artifact(plan_id: str, task_id: str) -> bool:
    """Remove artifact at db/{plan_id}/{task_id}/output.json. Returns True if deleted."""
    _validate_plan_id(plan_id)
    _validate_task_id(task_id)
    task_dir = _get_task_dir(plan_id, task_id)
    file_path = task_dir / "output.json"
    try:
        if file_path.exists():
            file_path.unlink()
            return True
    except OSError as e:
        logger.warning("Failed to delete artifact %s: %s", file_path, e)
    return False


async def save_validation_report(plan_id: str, task_id: str, report: dict) -> dict:
    """Save validation report to db/{plan_id}/{task_id}/validation.json."""
    _validate_plan_id(plan_id)
    _validate_task_id(task_id)
    task_dir = _get_task_dir(plan_id, task_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    file_path = task_dir / "validation.json"
    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    content = orjson.dumps(report, option=orjson.OPT_INDENT_2).decode("utf-8")
    async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
        await f.write(content)
    tmp_path.replace(file_path)
    return {"success": True}


async def _ensure_plan_dir(plan_id: str = DEFAULT_PLAN_ID) -> None:
    _validate_plan_id(plan_id)
    plan_dir = _get_plan_dir(plan_id)
    plan_dir.mkdir(parents=True, exist_ok=True)


async def _read_json_file(plan_id: str, filename: str):
    await _ensure_plan_dir(plan_id)
    file_path = _get_file_path(plan_id, filename)
    try:
        async with aiofiles.open(file_path, "rb") as f:
            data = await f.read()
            return orjson.loads(data)
    except FileNotFoundError:
        return None
    except orjson.JSONDecodeError as e:
        logger.warning("Invalid JSON in %s: %s", file_path, e)
        return None


async def _write_json_file(plan_id: str, filename: str, data: dict) -> dict:
    """Atomic write: write to .tmp then rename to avoid partial/corrupt files on concurrent access."""
    await _ensure_plan_dir(plan_id)
    file_path = _get_file_path(plan_id, filename)
    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    content = orjson.dumps(data, option=orjson.OPT_INDENT_2).decode("utf-8")
    async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
        await f.write(content)
    tmp_path.replace(file_path)
    return {"success": True}


async def get_execution(plan_id: str = DEFAULT_PLAN_ID):
    """Get execution."""
    return await _read_json_file(plan_id, "execution.json")


async def save_execution(execution: dict, plan_id: str = DEFAULT_PLAN_ID) -> dict:
    """Save execution."""
    await _write_json_file(plan_id, "execution.json", execution)
    return {"success": True, "execution": execution}


async def list_plan_ids() -> list:
    """List plan IDs from db/, sorted by plan.json mtime (newest first)."""
    if not DB_DIR.exists():
        return []
    result = []
    for p in DB_DIR.iterdir():
        if p.is_dir() and not p.name.startswith("."):
            plan_file = p / "plan.json"
            if plan_file.exists():
                try:
                    mtime = plan_file.stat().st_mtime
                    result.append((p.name, mtime))
                except OSError:
                    result.append((p.name, 0))
    result.sort(key=lambda x: x[1], reverse=True)
    return [pid for pid, _ in result]


def _ai_mode_to_flags(ai_mode: str) -> tuple:
    """Convert aiMode to (useMock, taskAgentMode, planAgentMode). aiMode: mock|llm|llmagent|agent."""
    if ai_mode == "mock":
        return True, False, False
    if ai_mode == "llmagent":
        return False, True, False  # Plan: LLM, Execute: Agent
    if ai_mode == "agent":
        return False, True, True  # Plan: Agent, Execute: Agent
    return False, False, False  # llm


def _resolve_config(raw: dict) -> dict:
    """Resolve presets+current to effective config for LLM/plan/execution. aiMode: mock|llm|llmagent|agent."""
    if not raw:
        return {}
    ai_mode = raw.get("aiMode") or "mock"
    use_mock, task_agent, plan_agent = _ai_mode_to_flags(ai_mode)

    presets = raw.get("presets")
    current = raw.get("current")
    if isinstance(presets, dict) and current and current in presets:
        cfg = dict(presets[current])
        cfg.pop("label", None)
    else:
        cfg = {}
    cfg["useMock"] = use_mock
    cfg["taskAgentMode"] = task_agent
    cfg["planAgentMode"] = plan_agent
    cfg["aiMode"] = ai_mode
    mode_config = raw.get("modeConfig") or {}
    cfg["modeConfig"] = mode_config
    v = raw.get("maxExecutionConcurrency")
    cfg["maxExecutionConcurrency"] = int(v) if v is not None else 7
    for m in ("llm", "llmagent", "agent"):
        pm = mode_config.get(m) or {}
        t = pm.get("planLlmTemperature")
        if t is not None:
            cfg["temperature"] = float(t)
            break
    return cfg


async def get_settings() -> dict:
    """Get full settings from db/settings.json. For frontend and other modules."""
    file_path = DB_DIR / SETTINGS_FILE
    try:
        async with aiofiles.open(file_path, "rb") as f:
            data = await f.read()
            return orjson.loads(data)
    except FileNotFoundError:
        return {}
    except orjson.JSONDecodeError as e:
        logger.warning("Invalid JSON in %s: %s", file_path, e)
        return {}


async def get_effective_config() -> dict:
    """Get effective config for LLM/plan/execution (resolves current preset from settings)."""
    raw = await get_settings()
    return _resolve_config(raw)


async def save_settings(settings: dict) -> dict:
    """Save settings to db/settings.json. Atomic write to avoid corruption."""
    file_path = DB_DIR / SETTINGS_FILE
    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    content = orjson.dumps(settings or {}, option=orjson.OPT_INDENT_2).decode("utf-8")
    async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
        await f.write(content)
    tmp_path.replace(file_path)
    return {"success": True}


async def get_plan(plan_id: str = DEFAULT_PLAN_ID):
    """Get plan (AI-refined idea with tasks)."""
    return await _read_json_file(plan_id, "plan.json")


async def save_plan(plan: dict, plan_id: str = DEFAULT_PLAN_ID) -> dict:
    """Save plan."""
    await _write_json_file(plan_id, "plan.json", plan)
    return {"success": True, "plan": plan}


# AI response persistence (atomicity, decompose, format) - per plan_id

_ai_save_locks: dict = {}


def _get_ai_save_lock(plan_id: str, response_type: str) -> asyncio.Lock:
    key = (plan_id, response_type)
    if key not in _ai_save_locks:
        _ai_save_locks[key] = asyncio.Lock()
    return _ai_save_locks[key]


async def _read_ai_response_file(plan_id: str, response_type: str) -> dict:
    """Read AI response file with json_repair fallback for corrupted files."""
    await _ensure_plan_dir(plan_id)
    file_path = _get_file_path(plan_id, f"{response_type}.json")
    try:
        async with aiofiles.open(file_path, "rb") as f:
            raw = await f.read()
        try:
            data = orjson.loads(raw)
        except orjson.JSONDecodeError:
            data = json_repair.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("Failed to read %s: %s", file_path, e)
        return {}


async def get_ai_responses(plan_id: str, response_type: str) -> dict:
    """Read AI responses for a plan. response_type: atomicity, decompose, format."""
    if response_type not in ("atomicity", "decompose", "format"):
        return {}
    return await _read_ai_response_file(plan_id, response_type)


async def _write_ai_response_file(plan_id: str, response_type: str, data: dict) -> None:
    """Atomic write: write to .tmp then rename."""
    await _ensure_plan_dir(plan_id)
    file_path = _get_file_path(plan_id, f"{response_type}.json")
    tmp_path = file_path.with_suffix(".json.tmp")
    content = orjson.dumps(data, option=orjson.OPT_INDENT_2).decode("utf-8")
    async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
        await f.write(content)
    tmp_path.rename(file_path)


async def save_ai_response(plan_id: str, response_type: str, key: str, entry: dict) -> None:
    """Incrementally save one AI response. entry = {content: ..., reasoning: ...}. Serialized per file."""
    if response_type not in ("atomicity", "decompose", "format"):
        return
    lock = _get_ai_save_lock(plan_id, response_type)
    async with lock:
        data = await get_ai_responses(plan_id, response_type)
        data[key] = entry
        await _write_ai_response_file(plan_id, response_type, data)


async def clear_db() -> dict:
    """Clear DB: remove all plan folders."""
    if not DB_DIR.exists():
        return {"success": True, "removed": []}
    removed = []
    for p in DB_DIR.iterdir():
        if not p.is_dir() or p.name.startswith("."):
            continue
        try:
            shutil.rmtree(p)
            removed.append(p.name)
        except OSError as e:
            logger.warning("Failed to remove %s: %s", p, e)
    return {"success": True, "removed": removed}
