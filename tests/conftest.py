"""Shared test fixtures.

Every test runs against a throwaway SQLite DB so the suite never touches the
dev or production database.
"""
import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DB_URL", f"sqlite:///{path}")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("INTERNAL_API_KEY", "")
    monkeypatch.setenv("TODY_SUPERVISED_AUTO_REPLY", "false")
    monkeypatch.setenv("TODY_WORKER_LIVE_CONFIRM", "")

    from app.config import get_settings
    get_settings.cache_clear()

    import app.db.models as models
    models._engine = None
    models.SessionLocal = None
    models.init_db()

    yield

    os.remove(path)
