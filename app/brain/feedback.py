"""Explicit user feedback commands for shaping the newborn brain."""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import CognitiveMemory, session_scope
from app.brain import nurture_engine
from app.memory import base_memory, behavior_memory, goal_memory


def apply_feedback(message: str) -> dict:
    """Handle explicit memory/personality commands when present."""
    text = (message or "").strip()
    lower = text.lower()

    if lower.startswith("remember this:"):
        content = text.split(":", 1)[1].strip()
        mem_id = base_memory.add(
            memory_type="belief",
            title=content[:120] or "remembered belief",
            content=content,
            project="PERSONAL",
            emotion_tag="growth",
            source_type="manual",
            importance_score=9,
            is_permanent=True,
        )
        return {"handled": True, "command": "remember", "memory_id": mem_id}

    if lower.startswith("correct your behavior:"):
        content = text.split(":", 1)[1].strip()
        mem_id = behavior_memory.remember_preference(
            title="Explicit behavior correction",
            content=f"Correction: {content}",
            importance=10,
        )
        return {"handled": True, "command": "correct_behavior", "memory_id": mem_id}

    if lower.startswith("set goal:"):
        content = text.split(":", 1)[1].strip()
        goal = goal_memory.create_goal(title=content, horizon="short", project="GENERAL")
        return {"handled": True, "command": "set_goal", "goal": goal}

    if lower.startswith("homework:"):
        content = text.split(":", 1)[1].strip()
        homework = nurture_engine.assign_homework(content)
        return {"handled": True, "command": "homework", "homework": homework}

    if lower.startswith("complete homework:"):
        content = text.split(":", 1)[1].strip()
        done = nurture_engine.complete_homework(content)
        return {"handled": True, "command": "complete_homework", "result": done}

    if lower.startswith("forget this:"):
        query = text.split(":", 1)[1].strip()
        archived = _archive_matching(query)
        return {"handled": True, "command": "forget", "archived": archived}

    return {"handled": False}


def _archive_matching(query: str, limit: int = 20) -> int:
    if not query:
        return 0
    like = f"%{query[:200]}%"
    with session_scope() as s:
        stmt = (
            select(CognitiveMemory)
            .where(CognitiveMemory.is_archived.is_(False))
            .where(
                (CognitiveMemory.title.like(like))
                | (CognitiveMemory.content.like(like))
            )
            .limit(limit)
        )
        rows = s.scalars(stmt).all()
        for row in rows:
            row.is_archived = True
        return len(rows)
