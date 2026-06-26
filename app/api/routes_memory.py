"""Memory routes — add and search cognitive memories."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.memory import base_memory

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryIn(BaseModel):
    memory_type: str = "episodic"
    title: str
    content: str
    project: str = "GENERAL"
    emotion_tag: str = "neutral"
    importance_score: int = 5
    is_permanent: bool = False
    lesson_learned: str | None = None
    future_action: str | None = None
    avoid_action: str | None = None


@router.post("/add")
def add_memory(m: MemoryIn) -> dict:
    mem_id = base_memory.add(
        memory_type=m.memory_type, title=m.title, content=m.content,
        project=m.project, emotion_tag=m.emotion_tag,
        importance_score=m.importance_score, is_permanent=m.is_permanent,
        lesson_learned=m.lesson_learned, future_action=m.future_action,
        avoid_action=m.avoid_action,
    )
    return {"saved": True, "memory_id": mem_id}


@router.get("/search")
def search_memory(query: str | None = None, memory_type: str | None = None,
                  project: str | None = None, limit: int = 20) -> dict:
    hits = base_memory.search(query=query, memory_type=memory_type,
                              project=project, limit=limit)
    return {"count": len(hits), "results": [h.__dict__ for h in hits]}


@router.get("/recall")
def recall_memory(text: str, project: str | None = None, limit: int = 5) -> dict:
    hits = base_memory.recall(text, project=project, limit=limit)
    return {"count": len(hits), "results": [h.__dict__ for h in hits]}
