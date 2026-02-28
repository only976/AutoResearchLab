from datetime import datetime
import re
from typing import Any, Dict, List, Optional

from backend.db.repository import (
    list_idea_snapshots,
    load_idea_snapshot,
    save_idea_snapshot,
)


def _extract_topic_title(topic_data: Any, refinement_data: Any = None) -> str:
    candidates: List[Any] = []

    if isinstance(topic_data, dict):
        candidates.extend(
            [
                topic_data.get("title"),
                topic_data.get("idea_name"),
                topic_data.get("topic"),
                topic_data.get("scope"),
                topic_data.get("tldr"),
                topic_data.get("abstract"),
            ]
        )
    elif isinstance(topic_data, str):
        candidates.append(topic_data)

    if isinstance(refinement_data, dict):
        candidates.extend(
            [
                refinement_data.get("title"),
                refinement_data.get("idea_name"),
                refinement_data.get("topic"),
                refinement_data.get("scope"),
                refinement_data.get("tldr"),
            ]
        )
    elif isinstance(refinement_data, str):
        candidates.append(refinement_data)

    for raw in candidates:
        if raw is None:
            continue
        value = str(raw).strip()
        if value:
            return value

    return "idea_snapshot"


def _sanitize_snapshot_name(raw_name: str) -> str:
    cleaned = (raw_name or "").strip()
    if cleaned.endswith(".json"):
        cleaned = cleaned[:-5]
    cleaned = " ".join(cleaned.split())
    cleaned = re.sub(r"[^\w\s-]", "_", cleaned)
    cleaned = "_".join(cleaned.split())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:80] or "idea_snapshot"

def save_snapshot(refinement_data: Any, results: Any, custom_name: Optional[str] = None) -> str:
    """Saves the current session state (refinement + ideas) to SQLite."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not custom_name:
        if results and len(results) > 0:
            topic_data = results[0].get("topic", {})
            title = _extract_topic_title(topic_data, refinement_data)

            safe_title = "".join([c if c.isalnum() or c == ' ' else "_" for c in title])
            safe_title = "_".join(safe_title.split())
            safe_title = safe_title[:50]
            if not safe_title:
                safe_title = "idea_snapshot"

            custom_name = f"{timestamp}_{safe_title}"
        else:
            custom_name = f"{timestamp}_empty"

    custom_name = _sanitize_snapshot_name(custom_name)

    if not custom_name.endswith(".json"):
        custom_name += ".json"

    data: Dict[str, Any] = {
        "timestamp": timestamp,
        "refinement_data": refinement_data,
        "results": results
    }

    save_idea_snapshot(custom_name, refinement_data, results, data)
    return custom_name

def list_snapshots() -> List[Dict[str, Any]]:
    """Returns snapshot metadata sorted by created time (newest first)."""
    return list_idea_snapshots()

def load_snapshot(filename: str) -> Optional[Dict[str, Any]]:
    """Loads a snapshot by name from SQLite."""
    return load_idea_snapshot(filename)
