"""TACHY Cognitive Brain OS V1 — FastAPI entrypoint.

Boots the app, exposes /health and /identity, and mounts the chat route.
Memory / decision / approval / reflection routes mount as their phases land.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.brain import identity_core
from app.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0-phase1a")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@app.get("/identity")
def identity() -> dict:
    return identity_core.describe()


# ── Routes ──────────────────────────────────────────────────────
from app.api import routes_chat  # noqa: E402

app.include_router(routes_chat.router)
