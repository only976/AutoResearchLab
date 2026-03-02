"""
Config module. Uses backend/db/config.json as single source of truth.
No env fallback - all config comes from config.json.
"""

import json
import uuid
from pathlib import Path
import os

# Storage in backend/db (unified)
DB_DIR = Path(__file__).resolve().parent / "db"
CONFIG_FILE = "config.json"
LLM_MODEL = "gemini-3-flash-preview"
LLM_API_BASE = None
LLM_API_KEY = os.getenv("GOOGLE_API_KEY")

def _config_path() -> Path:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return DB_DIR / CONFIG_FILE


def _default_config() -> dict:
    """Default config when file is missing."""
    return {
        "llm_model": "gemini-3-flash-preview",
        "llm_api_base": "",
        "llm_api_key": "",
        "frontend_port": 3030,
    }


def get_config() -> dict:
    """Read config from backend/db/config.json. Sync, for use in agents."""
    path = _config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except FileNotFoundError:
        return _default_config()
    except json.JSONDecodeError:
        pass
    return _default_config()


def save_config(config: dict) -> dict:
    """Save config to backend/db/config.json. Atomic write."""
    path = _config_path()
    merged = dict(_default_config())
    int_keys = {"frontend_port"}
    if isinstance(config, dict):
        for k, v in config.items():
            if k == "backend_port":
                continue  # fixed at 8888, do not persist
            if k in merged:
                if k in int_keys:
                    try:
                        merged[k] = int(v) if v is not None and str(v).strip() else merged[k]
                    except (ValueError, TypeError):
                        pass
                else:
                    merged[k] = v if isinstance(v, str) else str(v) if v is not None else ""
    tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    tmp.replace(path)
    return {"success": True}


def get_llm_config() -> dict:
    """Get effective LLM config for agents: model, api_base, api_key."""
    s = get_config()
    return {
        "model": (s.get("llm_model") or "").strip() or "gemini-3-flash-preview",
        "api_base": (s.get("llm_api_base") or "").strip() or None,
        "api_key": (s.get("llm_api_key") or "").strip() or None,
    }
