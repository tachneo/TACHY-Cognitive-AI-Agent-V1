"""Memory routes — add and search cognitive memories."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.memory import base_memory
from app.safety.audit_logger import log_event

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryIn(BaseModel):
    memory_type: Literal[
        "working", "episodic", "semantic", "procedural", "emotional",
        "decision", "failure", "interest", "behavior", "relationship",
        "project", "risk", "goal", "belief", "opportunity",
    ] = "episodic"
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=20000)
    project: str = Field(default="GENERAL", max_length=64)
    emotion_tag: str = Field(default="neutral", max_length=20)
    importance_score: int = Field(default=5, ge=0, le=10)
    is_permanent: bool = False
    lesson_learned: str | None = Field(default=None, max_length=5000)
    future_action: str | None = Field(default=None, max_length=5000)
    avoid_action: str | None = Field(default=None, max_length=5000)


@router.post("/add")
def add_memory(m: MemoryIn) -> dict:
    mem_id = base_memory.add(
        memory_type=m.memory_type, title=m.title, content=m.content,
        project=m.project, emotion_tag=m.emotion_tag,
        importance_score=m.importance_score, is_permanent=m.is_permanent,
        lesson_learned=m.lesson_learned, future_action=m.future_action,
        avoid_action=m.avoid_action,
    )
    log_event(
        "memory_added",
        detail=f"id={mem_id}; type={m.memory_type}; project={m.project}",
        risk_tier="medium" if m.is_permanent else "low",
    )
    return {"saved": True, "memory_id": mem_id}


@router.get("/search")
def search_memory(query: str | None = None, memory_type: str | None = None,
                  project: str | None = None,
                  limit: int = Query(default=20, ge=1, le=100)) -> dict:
    hits = base_memory.search(query=query, memory_type=memory_type,
                              project=project, limit=limit)
    return {"count": len(hits), "results": [h.__dict__ for h in hits]}


@router.get("/recall")
def recall_memory(text: str = Query(min_length=1, max_length=8000),
                  project: str | None = Query(default=None, max_length=64),
                  limit: int = Query(default=5, ge=1, le=25)) -> dict:
    hits = base_memory.recall(text, project=project, limit=limit)
    return {"count": len(hits), "results": [h.__dict__ for h in hits]}
