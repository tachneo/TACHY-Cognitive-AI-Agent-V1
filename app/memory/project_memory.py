"""Project memory — facts about each project (TODY, the brain, ERP-CRM, etc.)
so Shree has persistent project context: stack, status, open issues, decisions."""
from __future__ import annotations

from app.memory import base_memory


def remember_project_fact(*, project: str, fact: str, detail: str = "") -> int:
    content = f"fact: {fact[:200]}\ndetail: {detail[:300]}"
    return base_memory.add(
        memory_type="project", title=f"{project}: {fact}"[:255], content=content,
        project=project[:32].upper(), emotion_tag="trust",
        source_type="project", importance_score=6, is_permanent=True,
    )


def recall_project(project: str, limit: int = 20) -> list[dict]:
    hits = base_memory.search(memory_type="project", project=project[:32].upper(),
                              limit=limit)
    return [{"id": h.id, "title": h.title, "content": h.content}
            for h in hits]


def recall_project_facts(query: str, project: str | None = None,
                         limit: int = 8) -> list[dict]:
    hits = base_memory.recall_rich(query, limit=limit * 2)
    out = [{"id": h.id, "title": h.title, "content": h.content}
           for h in hits if h.memory_type == "project"]
    if project:
        out = [o for o in out if project.lower() in o["title"].lower()]
    return out[:limit]
