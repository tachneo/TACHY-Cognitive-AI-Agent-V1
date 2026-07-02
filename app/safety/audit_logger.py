"""Audit logger — append important safety/action events."""
from __future__ import annotations

from app.db.models import CognitiveAuditLog, session_scope


def log_event(
    action: str,
    *,
    detail: str | None = None,
    risk_tier: str = "low",
    actor: str = "system",
) -> int:
    """Persist an audit event and return its id."""
    with session_scope() as s:
        row = CognitiveAuditLog(
            actor=actor[:64],
            action=action[:255],
            detail=detail,
            risk_tier=risk_tier,
        )
        s.add(row)
        s.flush()
        return int(row.id)
