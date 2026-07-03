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
    # Hermetic LLM: force the offline heuristic provider so tests never make
    # real network calls (production .env has HF creds configured).
    monkeypatch.setenv("LLM_PROVIDER", "heuristic")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("HF_TOKEN", "")
    # Keep per-run state files out of the production storage/ tree.
    monkeypatch.setenv("EMOTION_MOOD_PATH", path + ".mood.json")
    monkeypatch.setenv("WEB_LEARNING_STATE_PATH", path + ".topics.json")
    monkeypatch.setenv("INNER_LIFE_STATE_PATH", path + ".inner.json")

    from app.config import get_settings
    get_settings.cache_clear()

    import app.db.models as models
    models._engine = None
    models.SessionLocal = None
    models.init_db()

    yield

    os.remove(path)
    for suffix in (".mood.json", ".topics.json", ".inner.json"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)
