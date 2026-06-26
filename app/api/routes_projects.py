"""Project / interest / behavior routes (read-only views into the brain)."""
from __future__ import annotations

from fastapi import APIRouter

from app.brain.interest_system import SEED_INTERESTS
from app.memory import base_memory

router = APIRouter(tags=["projects"])


@router.get("/projects/{project}/memory")
def project_memory(project: str, limit: int = 50) -> dict:
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
    # Seed behavior model from the plan; learning_engine will grow this later.
    patterns = [
        "Prefers practical, production-ready answers; dislikes generic ones.",
        "Wants Big-4 / Deloitte-level professional style for client replies.",
        "Wants direct business value and copy-pasteable prompts/code.",
        "Wants strong security and production readiness.",
        "Thinks as founder, CTO, CEO, product owner, and marketer together.",
    ]
    return {"count": len(patterns), "patterns": patterns}
