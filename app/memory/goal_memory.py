"""Goal memory subsystem."""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import CognitiveGoal, session_scope
from app.memory import base_memory


def create_goal(*, title: str, horizon: str = "short",
                project: str = "GENERAL") -> dict:
    """Persist a goal and mirror it into memory for recall."""
    with session_scope() as s:
        row = CognitiveGoal(title=title[:255], horizon=horizon,
                            project=project, status="open")
        s.add(row)
        s.flush()
        goal_id = int(row.id)

    mem_id = base_memory.add(
        memory_type="goal",
        title=title[:255],
        content=f"Goal #{goal_id}: {title} | horizon={horizon} | project={project}",
        project=project,
        emotion_tag="growth",
        source_type="system",
        importance_score=8,
        is_permanent=True,
    )
    return {
        "id": goal_id,
        "title": title[:255],
        "horizon": horizon,
        "status": "open",
        "project": project,
        "memory_id": mem_id,
    }


def list_goals(*, status: str | None = None, project: str | None = None,
               limit: int = 50) -> list[dict]:
    with session_scope() as s:
        stmt = select(CognitiveGoal).order_by(CognitiveGoal.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(CognitiveGoal.status == status)
        if project:
            stmt = stmt.where(CognitiveGoal.project == project)
        return [
            {
                "id": int(row.id),
                "title": row.title,
                "horizon": row.horizon,
                "status": row.status,
                "project": row.project,
                "created_at": str(row.created_at),
            }
            for row in s.scalars(stmt).all()
        ]


def update_goal_status(goal_id: int, status: str) -> dict:
    with session_scope() as s:
        row = s.get(CognitiveGoal, goal_id)
        if row is None:
            return {"error": "not_found", "id": goal_id}
        row.status = status
        return {"id": goal_id, "status": status}
