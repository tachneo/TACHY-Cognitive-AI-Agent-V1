"""Emotion routes — inspect and exercise the Emotion Intelligence Module."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.brain import emotion_engine

router = APIRouter(prefix="/emotion", tags=["emotion"])


class AppraiseIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@router.get("/state")
def state() -> dict:
    """Current mood baseline, taxonomy size, and the governing principle."""
    return emotion_engine.describe()


@router.post("/appraise")
def appraise(req: AppraiseIn) -> dict:
    """Run a standalone emotional appraisal (no reply, no decision)."""
    return emotion_engine.appraise(req.message)


@router.get("/taxonomy")
def taxonomy(category: str | None = None, q: str | None = None,
             limit: int = 50) -> dict:
    rows = emotion_engine.taxonomy_rows()
    if category:
        rows = tuple(r for r in rows if r.category.lower() == category.lower())
    if q:
        needle = q.lower()
        rows = tuple(r for r in rows if needle in r.name.lower()
                     or needle in r.agi_usage.lower())
    rows = rows[:max(1, min(limit, 400))]
    return {"count": len(rows), "emotions": [r.__dict__ for r in rows]}
