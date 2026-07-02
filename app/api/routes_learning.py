"""Learning routes — internet exploration and learned-knowledge review."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.brain import web_learning

router = APIRouter(prefix="/learn", tags=["learning"])


class ExploreIn(BaseModel):
    topic: str | None = Field(default=None, max_length=200)
    max_pages: int | None = Field(default=None, ge=1, le=5)


@router.post("/web")
def explore_web(req: ExploreIn) -> dict:
    """Learn from the internet now. Omit topic for a curiosity-driven pick."""
    return web_learning.explore(req.topic, max_pages=req.max_pages)


@router.get("/web/recent")
def recent_lessons(limit: int = 10) -> dict:
    return {"lessons": web_learning.recent(limit=max(1, min(limit, 50)))}


@router.get("/web/status")
def learning_status() -> dict:
    return web_learning.status()
