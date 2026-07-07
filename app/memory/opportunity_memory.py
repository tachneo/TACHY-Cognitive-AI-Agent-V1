"""Opportunity memory — opportunities Shree or Rohit spotted, so they persist
and can be recalled ('we talked about offering schools a flat-fee model')."""
from __future__ import annotations

from app.memory import base_memory


def remember_opportunity(*, title: str, detail: str, value: str = "",
                         importance: int = 6) -> int:
    content = f"detail: {detail[:300]}" + (f"\nvalue: {value[:120]}" if value else "")
    return base_memory.add(
        memory_type="opportunity", title=title[:255], content=content,
        project="BUSINESS", emotion_tag="interest", source_type="opportunity",
        importance_score=importance, is_permanent=False,
    )


def recall_opportunities(query: str = "", limit: int = 8) -> list[dict]:
    hits = base_memory.recall_rich(query, limit=limit * 2) if query \
        else base_memory.search(memory_type="opportunity", limit=limit)
    return [{"id": h.id, "title": h.title, "content": h.content}
            for h in hits if h.memory_type == "opportunity"][:limit]
