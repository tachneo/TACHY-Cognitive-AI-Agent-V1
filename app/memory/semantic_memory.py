"""Semantic memory subsystem — facts and learned knowledge.

Thin wrapper over base_memory with memory_type="semantic". Phase 1O gives it
its first real writer: the web-learning engine stores internet-learned
knowledge here, which base_memory.recall() then surfaces to ground replies.
"""
from __future__ import annotations

from app.memory import base_memory


def remember_fact(
    *,
    title: str,
    content: str,
    topic: str | None = None,
    source_type: str = "learning",
    project: str = "GENERAL",
    importance: int = 6,
    lesson_learned: str | None = None,
) -> int:
    """Persist a fact/knowledge memory and return its id."""
    return base_memory.add(
        memory_type="semantic",
        title=title,
        content=content,
        project=project,
        source_type=source_type,
        importance_score=importance,
        urgency_score=1,
        risk_score=1,
        interest_score=importance,
        lesson_learned=lesson_learned,
        related_module=topic,
    )


def recall_facts(query: str, *, limit: int = 5) -> list[base_memory.MemoryHit]:
    return [h for h in base_memory.recall(query, limit=limit * 2)
            if h.memory_type == "semantic"][:limit]
