import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_sqlite_db(tmp_path_factory):
    """Force backend/db/sqlite_backend.py to use a temp sqlite file for tests.

    Must run before importing backend modules that import sqlite_backend.
    """
    db_file = tmp_path_factory.mktemp("maars_test_db") / "maars_test.sqlite3"
    os.environ["MAARS_DB_PATH"] = str(db_file)
    yield


@pytest.fixture(scope="session", autouse=True)
def _isolate_logs_dir(tmp_path_factory):
    """Force backend/frontend logs to be written under a temp dir during tests."""
    logs_dir = tmp_path_factory.mktemp("maars_test_logs")
    os.environ["MAARS_LOGS_DIR"] = str(logs_dir)
    yield


@pytest.fixture(scope="session")
def logs_dir() -> Path:
    return Path(os.environ["MAARS_LOGS_DIR"]).resolve()


@pytest.fixture(scope="session")
def app():
    # Import after MAARS_DB_PATH is set.
    import main  # type: ignore

    return main.app


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def session_headers(client):
    r = client.post("/api/session/init")
    assert r.status_code == 200
    data = r.json()
    sid = data["sessionId"]
    tok = data["sessionToken"]
    return {
        "X-MAARS-SESSION-ID": sid,
        "X-MAARS-SESSION-TOKEN": tok,
    }


@pytest.fixture(autouse=True)
def clear_db_between_tests(client):
    # Best-effort clear so tests don't depend on ordering.
    client.post("/api/db/clear")
    yield
    client.post("/api/db/clear")


def _mock_settings_payload():
    return {
        "theme": "light",
        "agentMode": {
            "ideaAgent": "mock",
            "planAgent": "mock",
            "taskAgent": "mock",
            "paperAgent": "mock",
            "ideaRAG": False,
        },
        "reflection": {"enabled": False, "maxIterations": 1, "qualityThreshold": 70},
        "current": "test",
        "presets": {"test": {"label": "test", "baseUrl": "", "apiKey": "", "model": "mock"}},
    }


@pytest.fixture()
def use_mock_agents(client):
    r = client.post("/api/settings", json=_mock_settings_payload())
    assert r.status_code == 200
    yield
