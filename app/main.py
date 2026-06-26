"""TACHY Cognitive Brain OS V1 — FastAPI entrypoint.

Boots the app, exposes /health and /identity, and mounts the chat route.
Memory / decision / approval / reflection routes mount as their phases land.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.brain import identity_core
from app.config import get_settings
from app.db.models import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # create tables on first run (SQLite dev / fresh DB)
    yield


app = FastAPI(title=settings.app_name, version="1.1.0-phase1b", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@app.get("/identity")
def identity() -> dict:
    return identity_core.describe()


# ── Routes ──────────────────────────────────────────────────────
from app.api import (  # noqa: E402
    routes_agent, routes_approval, routes_chat, routes_decision,
    routes_memory, routes_projects, routes_reflection, routes_tody,
)

app.include_router(routes_chat.router)
app.include_router(routes_memory.router)
app.include_router(routes_decision.router)
app.include_router(routes_approval.router)
app.include_router(routes_reflection.router)
app.include_router(routes_projects.router)
app.include_router(routes_agent.router)
app.include_router(routes_tody.router)
