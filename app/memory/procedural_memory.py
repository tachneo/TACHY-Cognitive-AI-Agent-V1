"""Procedural memory — reusable skills/checklists (how to do X). Distinct from
correction_memory (which stores Rohit's corrections as rules); this stores
learned procedures Shree can follow again."""
from __future__ import annotations

from app.memory import base_memory


def remember_procedure(*, name: str, steps: list[str] | str,
                       when_to_use: str = "") -> int:
    body = steps if isinstance(steps, str) else "\n".join(f"- {s}" for s in steps)
    content = f"when: {when_to_use[:150]}\nsteps:\n{body[:600]}"
    return base_memory.add(
        memory_type="procedural", title=f"Procedure: {name}"[:255],
        content=content, project="PERSONAL", emotion_tag="neutral",
        source_type="procedural", importance_score=7, is_permanent=True,
        related_module=name[:120],
    )


def recall_procedures(query: str = "", limit: int = 10) -> list[dict]:
    hits = base_memory.recall_rich(query, limit=limit * 2) if query \
        else base_memory.search(memory_type="procedural", limit=limit)
    return [{"id": h.id, "title": h.title, "content": h.content}
            for h in hits if h.memory_type == "procedural"
            and h.title.startswith("Procedure:")][:limit]
