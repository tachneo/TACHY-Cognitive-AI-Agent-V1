"""Approval workflow — persist high-risk actions until Rohit decides.

The gate (approval_gate) decides *whether* approval is needed; this store records
the request and the guardian's response, with an audit trail.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app.db.models import CognitiveApproval, session_scope
from app.safety.approval_gate import evaluate
from app.safety.audit_logger import log_event


def request_approval(action: str, payload: str | None = None) -> dict:
    """Create a pending approval for `action` (records its risk tier)."""
    gate = evaluate(action)
    with session_scope() as s:
        row = CognitiveApproval(
            action=action, payload=payload, risk_tier=gate.tier.value,
            status="pending",
        )
        s.add(row)
        s.flush()
        approval_id = int(row.id)
    log_event(
        "approval_requested",
        detail=f"id={approval_id}; action={action}; payload={payload or ''}",
        risk_tier=gate.tier.value,
    )
    return {"id": approval_id, "action": action,
            "risk_tier": gate.tier.value, "status": "pending"}


def respond(approval_id: int, approved: bool) -> dict:
    """Record the guardian's decision on a pending approval."""
    with session_scope() as s:
        row = s.get(CognitiveApproval, approval_id)
        if row is None:
            return {"error": "not_found", "id": approval_id}
        if row.status != "pending":
            return {"id": approval_id, "status": row.status, "note": "already decided"}
        row.status = "approved" if approved else "rejected"
        row.decided_at = dt.datetime.now(dt.UTC)
        status = row.status
        action = row.action
        risk_tier = row.risk_tier
    log_event(
        "approval_decided",
        detail=f"id={approval_id}; action={action}; status={status}",
        risk_tier=risk_tier,
    )
    return {"id": approval_id, "status": status}


def list_pending(limit: int = 50) -> list[dict]:
    with session_scope() as s:
        stmt = (select(CognitiveApproval)
                .where(CognitiveApproval.status == "pending")
                .order_by(CognitiveApproval.requested_at.desc()).limit(limit))
        return [
            {"id": int(r.id), "action": r.action, "risk_tier": r.risk_tier,
             "payload": r.payload, "requested_at": str(r.requested_at)}
            for r in s.scalars(stmt).all()
        ]


def list_by_action(action: str, status: str | None = None,
                   limit: int = 50) -> list[dict]:
    with session_scope() as s:
        stmt = (
            select(CognitiveApproval)
            .where(CognitiveApproval.action == action)
            .order_by(CognitiveApproval.requested_at.desc())
            .limit(limit)
        )
        if status:
            stmt = stmt.where(CognitiveApproval.status == status)
        return [
            {
                "id": int(r.id),
                "action": r.action,
                "risk_tier": r.risk_tier,
                "status": r.status,
                "payload": r.payload,
                "requested_at": str(r.requested_at),
            }
            for r in s.scalars(stmt).all()
        ]


def get_approval(approval_id: int) -> dict | None:
    """Return an approval row as a plain dict."""
    with session_scope() as s:
        row = s.get(CognitiveApproval, approval_id)
        if row is None:
            return None
        return {
            "id": int(row.id),
            "action": row.action,
            "payload": row.payload,
            "risk_tier": row.risk_tier,
            "status": row.status,
            "requested_at": str(row.requested_at),
            "decided_at": str(row.decided_at) if row.decided_at else None,
        }
