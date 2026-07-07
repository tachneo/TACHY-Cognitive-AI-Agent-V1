"""Risk memory — risks Shree or Rohit identified, with severity + mitigation,
so known risks persist and can be recalled before risky actions."""
from __future__ import annotations

from app.memory import base_memory


def remember_risk(*, title: str, severity: int = 5, mitigation: str = "",
                  category: str = "production") -> int:
    content = f"severity: {severity}\ncategory: {category}\nmitigation: {mitigation[:200]}"
    return base_memory.add(
        memory_type="risk", title=title[:255], content=content,
        project="RISK", emotion_tag="fear", source_type="risk",
        importance_score=max(5, severity), is_permanent=True,
    )


def recall_risks(query: str = "", limit: int = 10) -> list[dict]:
    hits = base_memory.recall_rich(query, limit=limit * 2) if query \
        else base_memory.search(memory_type="risk", limit=limit)
    return [{"id": h.id, "title": h.title, "content": h.content}
            for h in hits if h.memory_type == "risk"][:limit]
