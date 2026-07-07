"""Audit logger — append important safety/action events.

``log_event`` persists to the cognitive audit table and raises on DB failure
(callers that already depend on the DB use this). ``log_event_safe`` never
raises: on DB failure it appends a JSONL line to a file fallback so the audit
trail is never silently lost — important for the coding agent, which can run
even when the DB is unavailable.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from app.db.models import CognitiveAuditLog, session_scope

_FALLBACK = Path("storage/logs/audit_fallback.log")


def set_fallback_path(path: str | Path) -> None:
    """Override the file-fallback path (used by tests)."""
    global _FALLBACK
    _FALLBACK = Path(path)


def log_event(
    action: str,
    *,
    detail: str | None = None,
    risk_tier: str = "low",
    actor: str = "system",
) -> int:
    """Persist an audit event and return its id. Raises on DB failure."""
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


def log_event_safe(
    action: str,
    *,
    detail: str | None = None,
    risk_tier: str = "low",
    actor: str = "system",
) -> int | None:
    """Best-effort audit. Returns the row id, or None if the DB was unavailable
    (in which case the event is appended to the file fallback instead)."""
    try:
        return log_event(action, detail=detail, risk_tier=risk_tier, actor=actor)
    except Exception:  # noqa: BLE001 — audit must never break the caller
        try:
            _FALLBACK.parent.mkdir(parents=True, exist_ok=True)
            with _FALLBACK.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": dt.datetime.now(dt.UTC).isoformat(),
                    "actor": (actor or "system")[:64],
                    "action": (action or "")[:255],
                    "detail": detail,
                    "risk_tier": risk_tier,
                }) + "\n")
        except Exception:  # noqa: BLE001
            pass
        return None
