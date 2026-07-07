"""Belief memory — things Shree holds to be true (about herself, the world,
Rohit, the work), so her stance is consistent across sessions rather than
re-derived each time."""
from __future__ import annotations

from app.memory import base_memory


def remember_belief(*, title: str, statement: str, grounds: str = "") -> int:
    content = f"belief: {statement[:300]}" + (f"\ngrounds: {grounds[:200]}" if grounds else "")
    return base_memory.add(
        memory_type="belief", title=title[:255], content=content,
        project="PERSONAL", emotion_tag="trust", source_type="belief",
        importance_score=7, is_permanent=True,
    )


def recall_beliefs(query: str = "", limit: int = 12) -> list[dict]:
    hits = base_memory.recall_rich(query, limit=limit * 2) if query \
        else base_memory.search(memory_type="belief", limit=limit)
    return [{"id": h.id, "title": h.title, "content": h.content}
            for h in hits if h.memory_type == "belief"][:limit]
