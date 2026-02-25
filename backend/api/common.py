import json
import os
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXPERIMENTS_DIR = os.path.join(PROJECT_ROOT, "data", "experiments")


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def read_json(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def write_json(path: str, data: Dict[str, Any]) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def parse_json_text(text: str) -> Dict[str, Any]:
    try:
        if isinstance(text, dict):
            return text
        # Try to find JSON object if mixed with text
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            json_str = text[start : end + 1]
            return json.loads(json_str)
        return json.loads(text)
    except Exception:
        return {"raw": text, "error": "Failed to parse JSON"}


def get_workspace_path(exp_id: str) -> str:
    return os.path.join(EXPERIMENTS_DIR, exp_id)


def list_experiments() -> List[Dict[str, Any]]:
    ensure_dir(EXPERIMENTS_DIR)
    items: List[Dict[str, Any]] = []
    for exp_id in os.listdir(EXPERIMENTS_DIR):
        path = get_workspace_path(exp_id)
        if not os.path.isdir(path):
            continue
            
        plan = read_json(os.path.join(path, "plan.json")) or {}
        status = read_json(os.path.join(path, "status.json")) or {}
        meta = read_json(os.path.join(path, "meta.json")) or {}
        
        # Determine title with fallback to meta
        title = (
            plan.get("title") 
            or plan.get("experiment_name") 
            or meta.get("idea", {}).get("title") 
            or meta.get("topic", {}).get("title") 
            or exp_id
        )
        
        # Parse creation time from exp_id (format: exp_YYYYMMDD_HHMMSS_...)
        created_at = None
        try:
            parts = exp_id.split("_")
            if len(parts) >= 3:
                date_str = parts[1]
                time_str = parts[2]
                # Format: YYYY-MM-DD HH:MM:SS
                created_at = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:]}"
        except Exception:
            pass
            
        items.append(
            {
                "id": exp_id,
                "title": title,
                "status": status.get("experiment_status", "initialized"),
                "updated_at": status.get("last_updated"),
                "created_at": created_at,
            }
        )
        
    # Sort by updated_at or created_at
    items.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)
    return items


def ensure_experiment_path(exp_id: str) -> str:
    workspace_path = get_workspace_path(exp_id)
    if not os.path.exists(workspace_path):
        raise HTTPException(status_code=404, detail="Experiment not found")
    return workspace_path


def safe_artifact_path(workspace_path: str, name: str) -> str:
    if os.path.sep in name or name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid artifact name")
    allowed = (".png", ".jpg", ".csv", ".json")
    if not name.endswith(allowed):
        raise HTTPException(status_code=400, detail="Unsupported artifact type")
    path = os.path.join(workspace_path, name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Artifact not found")
    return path
