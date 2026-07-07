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
    monkeypatch.setenv("TODY_AUTONOMOUS_SOCIAL", "false")
    monkeypatch.setenv("SELF_IMPROVE_AUTONOMOUS", "false")
    monkeypatch.setenv("TODY_WORKER_LIVE_CONFIRM", "")
    monkeypatch.setenv("TODY_NATIVE_TYPING_ENABLED", "false")
    # Hermetic LLM: force the offline heuristic provider so tests never make
    # real network calls (production .env has HF creds configured).
    monkeypatch.setenv("LLM_PROVIDER", "heuristic")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("HF_TOKEN", "")
    # Keep chat/coding on the offline provider in tests (never hit real Claude).
    monkeypatch.setenv("CHAT_PROVIDER", "default")
    monkeypatch.setenv("CHAT_ANTHROPIC_KEY", "")
    monkeypatch.setenv("CODING_ANTHROPIC_KEY", "")
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    # Keep per-run state files out of the production storage/ tree.
    monkeypatch.setenv("EMOTION_MOOD_PATH", path + ".mood.json")
    monkeypatch.setenv("WEB_LEARNING_STATE_PATH", path + ".topics.json")
    monkeypatch.setenv("INNER_LIFE_STATE_PATH", path + ".inner.json")
    monkeypatch.setenv("CURRICULUM_STATE_PATH", path + ".curriculum.json")
    monkeypatch.setenv("CURRICULUM_DAILY_STATE_PATH", path + ".curriculum_daily")

    from app.config import get_settings
    get_settings.cache_clear()

    import app.db.models as models
    models._engine = None
    models.SessionLocal = None
    models.init_db()

    yield

    os.remove(path)
    for suffix in (".mood.json", ".topics.json", ".inner.json",
                   ".curriculum.json", ".curriculum_daily"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)
