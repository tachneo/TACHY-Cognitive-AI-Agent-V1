"""Behavior memory subsystem."""
from __future__ import annotations

from app.memory import base_memory


def remember_preference(*, title: str, content: str, importance: int = 8) -> int:
    return base_memory.add(
        memory_type="behavior",
        title=title,
        content=content,
        project="PERSONAL",
        emotion_tag="growth",
        source_type="chat",
        importance_score=importance,
        is_permanent=True,
    )


def recall_preferences(text: str, limit: int = 5) -> list[dict]:
    hits = base_memory.recall(text, project="PERSONAL", limit=limit)
    return [
        {"id": h.id, "title": h.title, "content": h.content, "score": h.score}
        for h in hits
        if h.memory_type == "behavior"
    ]
