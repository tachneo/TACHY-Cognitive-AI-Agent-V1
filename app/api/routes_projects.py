"""Project / interest / behavior routes (read-only views into the brain)."""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.brain.personality import synthesize_profile
from app.brain.interest_system import SEED_INTERESTS
from app.memory import base_memory, goal_memory
from app.safety.audit_logger import log_event

router = APIRouter(tags=["projects"])


@router.get("/projects/{project}/memory")
def project_memory(project: str, limit: int = Query(default=50, ge=1, le=100)) -> dict:
    hits = base_memory.search(project=project, limit=limit)
    return {"project": project, "count": len(hits),
            "results": [h.__dict__ for h in hits]}


@router.get("/interests")
def interests() -> dict:
    items = sorted(SEED_INTERESTS.items(), key=lambda kv: kv[1], reverse=True)
    return {"count": len(items),
            "interests": [{"topic": t, "score": s} for t, s in items]}


@router.get("/behavior-patterns")
def behavior_patterns() -> dict:
    profile = synthesize_profile()
    return {"count": len(profile["traits"]), "profile": profile}


class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    horizon: str = Field(default="short", pattern="^(short|mid|long)$")
    project: str = Field(default="GENERAL", max_length=64)


@router.post("/goals")
def create_goal(req: GoalIn) -> dict:
    goal = goal_memory.create_goal(
        title=req.title, horizon=req.horizon, project=req.project
    )
    log_event("goal_created", detail=f"id={goal['id']}; project={goal['project']}")
    return {"saved": True, "goal": goal}


@router.get("/goals")
def goals(status: str | None = Query(default=None, max_length=16),
          project: str | None = Query(default=None, max_length=64),
          limit: int = Query(default=50, ge=1, le=100)) -> dict:
    rows = goal_memory.list_goals(status=status, project=project, limit=limit)
    return {"count": len(rows), "goals": rows}


@router.get("/personality")
def personality() -> dict:
    return synthesize_profile()
