"""Approval workflow — persist high-risk actions until Rohit decides.

The gate (approval_gate) decides *whether* approval is needed; this store records
the request and the guardian's response, with an audit trail.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select, update

from app.db.models import CognitiveApproval, session_scope
from app.safety.approval_gate import evaluate
from app.safety.audit_logger import log_event, log_event_safe


EXECUTION_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "superseded"})


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


def claim_execution(
    approval_id: int,
    *,
    expected_action: str,
    expected_payload: str | None,
) -> dict:
    """Atomically consume an approved authorization for one execution attempt.

    The conditional UPDATE is the compare-and-set boundary.  Only one process
    can move a row from ``approved`` to ``executing``; every concurrent or
    repeated caller observes the resulting non-approved state and is blocked.
    Action and payload predicates prevent the wrong executor from consuming a
    valid authorization.
    """
    now = dt.datetime.now(dt.UTC)
    with session_scope() as s:
        stmt = (
            update(CognitiveApproval)
            .where(
                CognitiveApproval.id == approval_id,
                CognitiveApproval.status == "approved",
                CognitiveApproval.action == expected_action,
                CognitiveApproval.payload == expected_payload,
            )
            .values(status="executing", execution_started_at=now)
        )
        changed = s.execute(stmt).rowcount == 1
        row = s.get(CognitiveApproval, approval_id)
        if row is None:
            outcome = {
                "id": approval_id,
                "claimed": False,
                "status": "not_found",
            }
        else:
            outcome = {
                "id": approval_id,
                "claimed": changed,
                "status": "executing" if changed else row.status,
                "action": row.action,
                "risk_tier": row.risk_tier,
            }

    if outcome["claimed"]:
        log_event_safe(
            "approval_execution_claimed",
            detail=f"id={approval_id}; action={expected_action}",
            risk_tier=str(outcome.get("risk_tier") or "high"),
        )
    return outcome


def complete_execution(approval_id: int, *, succeeded: bool) -> dict:
    """Atomically finish a claimed execution; terminal states are immutable."""
    final_status = "succeeded" if succeeded else "failed"
    now = dt.datetime.now(dt.UTC)
    with session_scope() as s:
        stmt = (
            update(CognitiveApproval)
            .where(
                CognitiveApproval.id == approval_id,
                CognitiveApproval.status == "executing",
            )
            .values(status=final_status, execution_completed_at=now)
        )
        changed = s.execute(stmt).rowcount == 1
        row = s.get(CognitiveApproval, approval_id)
        if row is None:
            outcome = {
                "id": approval_id,
                "completed": False,
                "status": "not_found",
            }
        else:
            outcome = {
                "id": approval_id,
                "completed": changed,
                "status": final_status if changed else row.status,
                "action": row.action,
                "risk_tier": row.risk_tier,
            }

    if outcome["completed"]:
        log_event_safe(
            "approval_execution_completed",
            detail=f"id={approval_id}; status={final_status}",
            risk_tier=str(outcome.get("risk_tier") or "high"),
        )
    return outcome


def supersede(
    approval_id: int,
    *,
    expected_action: str,
    expected_payload: str | None,
) -> dict:
    """Retire an unused approval that was replaced by new bound approvals.

    This transition is conditional on identity, payload, and a non-executing
    state.  A caller that loses a race to execution must not proceed with the
    replacement operation.
    """
    now = dt.datetime.now(dt.UTC)
    with session_scope() as s:
        stmt = (
            update(CognitiveApproval)
            .where(
                CognitiveApproval.id == approval_id,
                CognitiveApproval.status.in_(("pending", "approved")),
                CognitiveApproval.action == expected_action,
                CognitiveApproval.payload == expected_payload,
            )
            .values(
                status="superseded",
                decided_at=now,
                execution_completed_at=now,
            )
        )
        changed = s.execute(stmt).rowcount == 1
        row = s.get(CognitiveApproval, approval_id)
        if row is None:
            outcome = {
                "id": approval_id,
                "superseded": False,
                "status": "not_found",
            }
        else:
            outcome = {
                "id": approval_id,
                "superseded": changed,
                "status": "superseded" if changed else row.status,
                "action": row.action,
                "risk_tier": row.risk_tier,
            }

    if outcome["superseded"]:
        log_event_safe(
            "approval_superseded",
            detail=f"id={approval_id}; action={expected_action}",
            risk_tier=str(outcome.get("risk_tier") or "high"),
        )
    return outcome


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
            "execution_started_at": (
                str(row.execution_started_at) if row.execution_started_at else None
            ),
            "execution_completed_at": (
                str(row.execution_completed_at) if row.execution_completed_at else None
            ),
        }
