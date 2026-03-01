import os
import sqlite3
from contextlib import contextmanager

# Storage in backend/db (unified)
DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__)))
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
            """
        )
