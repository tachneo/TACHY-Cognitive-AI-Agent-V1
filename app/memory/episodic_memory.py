"""Episodic memory — general events (distinct from dialogue_memory, which is
TODY-conversation-specific). Stores notable happenings and recalls them by
topic so Shree has a personal timeline of events."""
from __future__ import annotations

from app.memory import base_memory


def remember_event(*, title: str, what: str, where: str = "",
                   person: str | None = None, importance: int = 6) -> int:
    content = f"what: {what[:300]}" + (f"\nwhere: {where[:120]}" if where else "")
    return base_memory.add(
        memory_type="episodic", title=title[:255], content=content,
        project="PERSONAL", emotion_tag="neutral", source_type="event",
        importance_score=importance, is_permanent=False,
        related_person=person,
    )


def recall_events(query: str = "", limit: int = 8) -> list[dict]:
    hits = base_memory.recall_rich(query, limit=limit * 2) if query \
        else base_memory.search(memory_type="episodic", limit=limit)
    return [{"id": h.id, "title": h.title, "content": h.content,
             "person": None} for h in hits if h.memory_type == "episodic"][:limit]
