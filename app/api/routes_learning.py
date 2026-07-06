"""Learning routes — internet exploration and learned-knowledge review."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.brain import curriculum_learning, web_learning

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


class CurriculumQuestionIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@router.get("/curriculum/plan")
def curriculum_plan() -> dict:
    return curriculum_learning.plan()


@router.get("/curriculum/status")
def curriculum_status() -> dict:
    return curriculum_learning.status()


@router.post("/curriculum/study-today")
def curriculum_study_today() -> dict:
    return curriculum_learning.study_today()


@router.post("/curriculum/exam")
def curriculum_exam(level: str | None = None) -> dict:
    return curriculum_learning.take_exam(level)


@router.post("/curriculum/answer")
def curriculum_answer(req: CurriculumQuestionIn) -> dict:
    return curriculum_learning.answer_offline(req.question)


@router.get("/curriculum/report")
def curriculum_report() -> dict:
    return curriculum_learning.daily_report()
