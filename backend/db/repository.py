import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.db.sqlite import get_conn


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _to_json(data: Any) -> str:
    return json.dumps(data if data is not None else {}, ensure_ascii=False)


def _from_json(data: Optional[str], default: Any) -> Any:
    if not data:
        return default
    try:
        return json.loads(data)
    except Exception:
        return default


def save_idea_snapshot(name: str, refinement_data: Any, results: Any, raw: Dict[str, Any]) -> None:
    created_at = _now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO idea_snapshots(name, created_at, refinement_data_json, results_json, raw_json)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                refinement_data_json=excluded.refinement_data_json,
                results_json=excluded.results_json,
                raw_json=excluded.raw_json
            """,
            (name, created_at, _to_json(refinement_data), _to_json(results), _to_json(raw)),
        )


def list_idea_snapshots() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name, created_at FROM idea_snapshots ORDER BY created_at DESC"
        ).fetchall()
    items: List[Dict[str, Any]] = []
    for row in rows:
        name = row["name"]
        title = name.replace(".json", "").split("_", 2)
        display_title = title[2].replace("_", " ") if len(title) > 2 else name
        items.append({
            "filename": name,
            "title": display_title,
            "timestamp": row["created_at"],
        })
    return items


def load_idea_snapshot(name: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT raw_json FROM idea_snapshots WHERE name = ?",
            (name,),
        ).fetchone()
    if not row:
        return None
    return _from_json(row["raw_json"], None)
