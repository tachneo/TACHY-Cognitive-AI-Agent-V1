"""Interest memory — persistent interest topics and scores, so Shree's
curiosity persists across sessions and she can report what she cares about."""
from __future__ import annotations

from app.memory import base_memory


def remember_interest(*, topic: str, score: int = 6, reason: str = "") -> int:
    content = f"interest_score: {score}\nreason: {reason[:200]}"
    return base_memory.add(
        memory_type="interest", title=topic[:255], content=content,
        project="PERSONAL", emotion_tag="interest", source_type="interest",
        importance_score=score, is_permanent=True,
        related_module=topic[:120],
    )


def recall_interests(limit: int = 12) -> list[dict]:
    hits = base_memory.search(memory_type="interest", limit=limit)
    return [{"id": h.id, "topic": h.title, "content": h.content}
            for h in hits]


def top_interests(n: int = 5) -> list[str]:
    return [i["topic"] for i in recall_interests(limit=n * 3)][:n]
