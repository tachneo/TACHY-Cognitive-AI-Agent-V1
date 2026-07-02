"""Emotional memory subsystem."""
from __future__ import annotations

from app.memory import base_memory


def remember_emotion(*, title: str, content: str, emotion: str,
                     importance: int = 6) -> int:
    return base_memory.add(
        memory_type="emotional",
        title=title,
        content=content,
        project="PERSONAL",
        emotion_tag=emotion,
        source_type="chat",
        importance_score=importance,
        is_permanent=False,
    )
