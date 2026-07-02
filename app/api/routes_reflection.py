"""Reflection route — run the daily learning loop."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.brain import nurture_engine
from app.brain.learning_engine import daily_reflection
from app.safety.audit_logger import log_event

router = APIRouter(prefix="/reflection", tags=["reflection"])


@router.post("/daily")
def daily() -> dict:
    result = daily_reflection()
    log_event(
        "daily_reflection",
        detail=f"saved={result.get('saved')}",
        risk_tier="low",
    )
    return result


class HomeworkIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    project: str = Field(default="PERSONAL", max_length=64)


@router.get("/care-profile")
def care_profile() -> dict:
    return nurture_engine.care_profile()


@router.post("/homework")
def assign_homework(req: HomeworkIn) -> dict:
    result = nurture_engine.assign_homework(req.title, project=req.project)
    log_event("homework_assigned", detail=f"id={result['id']}; project={req.project}")
    return {"saved": True, "homework": result}


@router.post("/daily-skill")
def daily_skill() -> dict:
    result = nurture_engine.learn_daily_skill()
    log_event("daily_skill", detail=f"learned={result.get('learned')}")
    return result


@router.post("/growth-report")
def growth_report() -> dict:
    result = nurture_engine.daily_growth_report()
    log_event("growth_report", detail=f"memory_id={result.get('memory_id')}")
    return result
