import os
import sqlite3
from contextlib import contextmanager

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_DIR = os.path.join(PROJECT_ROOT, "data", "db")
DB_PATH = os.path.join(DB_DIR, "autoresearchlab.sqlite3")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def get_conn():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    os.makedirs(DB_DIR, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS idea_snapshots (
                name TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                refinement_data_json TEXT,
                results_json TEXT,
                raw_json TEXT
            );

            CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title TEXT,
                meta_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS experiment_plans (
                exp_id TEXT PRIMARY KEY,
                updated_at TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                FOREIGN KEY(exp_id) REFERENCES experiments(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS experiment_status (
                exp_id TEXT PRIMARY KEY,
                updated_at TEXT NOT NULL,
                status_json TEXT NOT NULL,
                FOREIGN KEY(exp_id) REFERENCES experiments(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS experiment_conclusions (
                exp_id TEXT PRIMARY KEY,
                updated_at TEXT NOT NULL,
                conclusion_json TEXT NOT NULL,
                FOREIGN KEY(exp_id) REFERENCES experiments(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS experiment_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exp_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                line TEXT NOT NULL,
                FOREIGN KEY(exp_id) REFERENCES experiments(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_experiment_logs_exp_created
            ON experiment_logs(exp_id, id);

            CREATE TABLE IF NOT EXISTS experiment_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exp_id TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT,
                stage TEXT,
                step_id TEXT,
                summary TEXT,
                for_next_stage INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(exp_id, name),
                FOREIGN KEY(exp_id) REFERENCES experiments(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS experiment_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exp_id TEXT NOT NULL,
                feedback_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL,
                processed_at TEXT,
                UNIQUE(exp_id, feedback_id),
                FOREIGN KEY(exp_id) REFERENCES experiments(id) ON DELETE CASCADE
            );
            """
        )
