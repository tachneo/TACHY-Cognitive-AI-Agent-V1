"""TACHY Cognitive Brain OS V1 — FastAPI entrypoint.

Boots the app, exposes /health and /identity, and mounts the chat route.
Memory / decision / approval / reflection routes mount as their phases land.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.brain import identity_core
from app.config import get_settings
from app.db.models import init_db
from app.safety.auth import require_internal_api_key

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # create tables on first run (SQLite dev / fresh DB)
    yield


app = FastAPI(title=settings.app_name, version="1.1.0-phase1b", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@app.get("/identity", dependencies=[Depends(require_internal_api_key)])
def identity() -> dict:
    return identity_core.describe()


# ── Routes ──────────────────────────────────────────────────────
from app.api import (  # noqa: E402
    routes_agent, routes_approval, routes_behavior, routes_chat,
    routes_decision, routes_emotion, routes_inner, routes_learning,
    routes_memory, routes_projects, routes_reflection, routes_tody,
)

protected = [Depends(require_internal_api_key)]
app.include_router(routes_chat.router, dependencies=protected)
app.include_router(routes_memory.router, dependencies=protected)
app.include_router(routes_decision.router, dependencies=protected)
app.include_router(routes_approval.router, dependencies=protected)
app.include_router(routes_reflection.router, dependencies=protected)
app.include_router(routes_projects.router, dependencies=protected)
app.include_router(routes_agent.router, dependencies=protected)
app.include_router(routes_tody.router, dependencies=protected)
app.include_router(routes_learning.router, dependencies=protected)
app.include_router(routes_emotion.router, dependencies=protected)
app.include_router(routes_behavior.router, dependencies=protected)
app.include_router(routes_inner.router, dependencies=protected)
