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


def _iso_to_unix_seconds(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except Exception:
        return None


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


def upsert_experiment(exp_id: str, meta: Dict[str, Any], title: Optional[str] = None) -> None:
    meta = meta or {"id": exp_id}
    now = _now_iso()
    resolved_title = title or meta.get("idea", {}).get("title") or meta.get("topic", {}).get("title") or exp_id
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO experiments(id, created_at, updated_at, title, meta_json)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                updated_at=excluded.updated_at,
                title=excluded.title,
                meta_json=excluded.meta_json
            """,
            (exp_id, now, now, resolved_title, _to_json(meta)),
        )


def get_experiment(exp_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, created_at, updated_at, title, meta_json FROM experiments WHERE id = ?",
            (exp_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "title": row["title"],
        "meta": _from_json(row["meta_json"], {}),
    }


def _ensure_experiment_exists(exp_id: str) -> None:
    if get_experiment(exp_id):
        return
    upsert_experiment(exp_id, {"id": exp_id}, title=exp_id)


def list_experiment_rows() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT e.id, e.title, e.created_at, e.updated_at, s.status_json
            FROM experiments e
            LEFT JOIN experiment_status s ON s.exp_id = e.id
            ORDER BY e.updated_at DESC
            """
        ).fetchall()

    items: List[Dict[str, Any]] = []
    for row in rows:
        status = _from_json(row["status_json"], {})
        items.append(
            {
                "id": row["id"],
                "title": row["title"] or row["id"],
                "status": status.get("experiment_status", "initialized"),
                "updated_at": status.get("last_updated") or _iso_to_unix_seconds(row["updated_at"]),
                "created_at": row["created_at"],
            }
        )
    return items


def upsert_experiment_plan(exp_id: str, plan: Dict[str, Any]) -> None:
    _ensure_experiment_exists(exp_id)
    now = _now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO experiment_plans(exp_id, updated_at, plan_json)
            VALUES(?, ?, ?)
            ON CONFLICT(exp_id) DO UPDATE SET
                updated_at=excluded.updated_at,
                plan_json=excluded.plan_json
            """,
            (exp_id, now, _to_json(plan)),
        )
    if isinstance(plan, dict):
        existing = get_experiment(exp_id)
        existing_meta = existing.get("meta", {}) if existing else {"id": exp_id}
        upsert_experiment(exp_id, existing_meta, title=plan.get("title") or plan.get("experiment_name"))


def get_experiment_plan(exp_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT plan_json FROM experiment_plans WHERE exp_id = ?",
            (exp_id,),
        ).fetchone()
    if not row:
        return None
    return _from_json(row["plan_json"], None)


def upsert_experiment_status(exp_id: str, status: Dict[str, Any]) -> None:
    _ensure_experiment_exists(exp_id)
    now = _now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO experiment_status(exp_id, updated_at, status_json)
            VALUES(?, ?, ?)
            ON CONFLICT(exp_id) DO UPDATE SET
                updated_at=excluded.updated_at,
                status_json=excluded.status_json
            """,
            (exp_id, now, _to_json(status)),
        )


def get_experiment_status(exp_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status_json FROM experiment_status WHERE exp_id = ?",
            (exp_id,),
        ).fetchone()
    if not row:
        return None
    return _from_json(row["status_json"], None)


def upsert_experiment_conclusion(exp_id: str, conclusion: Dict[str, Any]) -> None:
    _ensure_experiment_exists(exp_id)
    now = _now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO experiment_conclusions(exp_id, updated_at, conclusion_json)
            VALUES(?, ?, ?)
            ON CONFLICT(exp_id) DO UPDATE SET
                updated_at=excluded.updated_at,
                conclusion_json=excluded.conclusion_json
            """,
            (exp_id, now, _to_json(conclusion)),
        )


def get_experiment_conclusion(exp_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT conclusion_json FROM experiment_conclusions WHERE exp_id = ?",
            (exp_id,),
        ).fetchone()
    if not row:
        return None
    return _from_json(row["conclusion_json"], None)


def append_experiment_log(exp_id: str, line: str) -> None:
    _ensure_experiment_exists(exp_id)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO experiment_logs(exp_id, created_at, line) VALUES(?, ?, ?)",
            (exp_id, _now_iso(), line),
        )


def get_experiment_logs(exp_id: str, limit: int = 200) -> List[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT line FROM experiment_logs WHERE exp_id = ? ORDER BY id DESC LIMIT ?",
            (exp_id, limit),
        ).fetchall()
    lines = [row["line"] for row in reversed(rows)]
    return lines


def upsert_experiment_artifact(
    exp_id: str,
    name: str,
    artifact_type: str,
    stage: Optional[str] = None,
    step_id: Optional[str] = None,
    summary: Optional[str] = None,
    for_next_stage: bool = False,
) -> None:
    _ensure_experiment_exists(exp_id)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO experiment_artifacts(exp_id, name, type, stage, step_id, summary, for_next_stage, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(exp_id, name) DO UPDATE SET
                type=excluded.type,
                stage=excluded.stage,
                step_id=excluded.step_id,
                summary=excluded.summary,
                for_next_stage=excluded.for_next_stage
            """,
            (
                exp_id,
                name,
                artifact_type,
                stage,
                step_id,
                summary,
                1 if for_next_stage else 0,
                _now_iso(),
            ),
        )


def list_experiment_artifacts(exp_id: str) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT name, type, stage, step_id, summary, for_next_stage, created_at
            FROM experiment_artifacts
            WHERE exp_id = ?
            ORDER BY id DESC
            """,
            (exp_id,),
        ).fetchall()
    return [
        {
            "name": row["name"],
            "type": row["type"],
            "stage": row["stage"],
            "step_id": row["step_id"],
            "summary": row["summary"],
            "for_next_stage": bool(row["for_next_stage"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def add_feedback(exp_id: str, feedback_id: str, feedback_type: str, message: str) -> Dict[str, Any]:
    _ensure_experiment_exists(exp_id)
    now = _now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO experiment_feedback(exp_id, feedback_id, created_at, type, message, status)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (exp_id, feedback_id, now, feedback_type, message, "pending"),
        )

    return {
        "id": feedback_id,
        "timestamp": now,
        "type": feedback_type,
        "message": message,
        "status": "pending",
    }


def get_pending_feedback(exp_id: str) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT feedback_id, created_at, type, message, status
            FROM experiment_feedback
            WHERE exp_id = ? AND status = 'pending'
            ORDER BY id ASC
            """,
            (exp_id,),
        ).fetchall()
    return [
        {
            "id": row["feedback_id"],
            "timestamp": row["created_at"],
            "type": row["type"],
            "message": row["message"],
            "status": row["status"],
        }
        for row in rows
    ]


def mark_feedback_processed(exp_id: str, feedback_id: str, action_taken: str = "processed") -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE experiment_feedback
            SET status = ?, processed_at = ?
            WHERE exp_id = ? AND feedback_id = ?
            """,
            (action_taken, _now_iso(), exp_id, feedback_id),
        )
