import os
import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """FastAPI TestClient with isolated config/sqlite and MAARS disabled.

    - Redirects backend config + sqlite DB into tmp_path.
    - Stubs MAARS Socket.IO attachment to avoid importing heavy MAARS modules.

    This keeps tests fast/offline and prevents writing into the repo.
    """

    # 1) Isolate SQLite used by backend.db.sqlite
    import backend.db.sqlite as sqlite

    sqlite_dir = tmp_path / "sqlite"
    sqlite_dir.mkdir(parents=True, exist_ok=True)
    sqlite.DB_DIR = str(sqlite_dir)
    sqlite.DB_PATH = str(sqlite_dir / "autoresearchlab.sqlite3")

    # 2) Isolate config file used by backend.config
    import backend.config as cfg

    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg.DB_DIR = cfg_dir

    # 3) Disable MAARS initialization in backend.main import
    import backend.maars_integration as mi
    import socketio

    def _stub_attach_maars(app):
        return socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

    monkeypatch.setattr(mi, "attach_maars", _stub_attach_maars, raising=True)

    # 4) Reload backend.main so it picks up patched paths/stubs
    import backend.main as main

    importlib.reload(main)

    return TestClient(main.app)
