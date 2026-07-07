"""Decision memory — past decisions and their outcomes, so Shree can recall
'last time I chose X, it worked/failed' instead of re-reasoning from scratch."""
from __future__ import annotations

from app.memory import base_memory


def remember_decision(*, title: str, chosen: str, reason: str = "",
                      outcome: str = "", project: str = "GENERAL") -> int:
    content = f"chose: {chosen[:200]}\nreason: {reason[:200]}\noutcome: {outcome[:200]}"
    return base_memory.add(
        memory_type="decision", title=title[:255], content=content,
        project=project, emotion_tag="trust", source_type="decision",
        importance_score=7, is_permanent=True,
    )


def recall_decisions(query: str = "", limit: int = 8) -> list[dict]:
    hits = base_memory.recall_rich(query, limit=limit * 2) if query \
        else base_memory.search(memory_type="decision", limit=limit)
    return [{"id": h.id, "title": h.title, "content": h.content}
            for h in hits if h.memory_type == "decision"][:limit]


def recall_similar_decisions(context: str, limit: int = 5) -> list[dict]:
    return recall_decisions(context, limit=limit)
