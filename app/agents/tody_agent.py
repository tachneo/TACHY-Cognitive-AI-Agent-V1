"""TODY agent — the brain's controlled connection to the TODY app.

Read actions (status/conversations/contacts) run freely. Outbound actions
(send a message, create a post) are HIGH-RISK by policy, so they never fire
directly: they create an approval request, and only execute once Rohit approves.
This is the Phase-1D guardrail before any TODY automation.
"""
from __future__ import annotations

from app.integrations.tody_client import TodyError, get_client
from app.safety import approvals


def connect() -> dict:
    """Authenticate and return the connected TODY identity (read-only)."""
    try:
        user = get_client().login()
        return {"connected": True,
                "as": {"username": user.get("username"),
                       "display_name": user.get("display_name"),
                       "uuid": user.get("uuid")}}
    except TodyError as e:
        return {"connected": False, "error": str(e)}


def status() -> dict:
    """Current account profile (read)."""
    return get_client().me()


def inbox(limit: int = 20) -> dict:
    """Recent conversations (read)."""
    return get_client().conversations(limit=limit)


def request_send(conversation_id: int, body: str) -> dict:
    """Outbound message → creates a pending approval, does NOT send."""
    payload = f"conversation_id={conversation_id}; body={body[:500]}"
    appr = approvals.request_approval("send_message", payload=payload)
    return {"queued": True, "approval": appr,
            "note": "Message will send only after this approval is approved."}


def execute_send(approval_id: int, conversation_id: int, body: str) -> dict:
    """Send a message ONLY if the referenced approval is approved."""
    pending = {a["id"] for a in approvals.list_pending()}
    if approval_id in pending:
        return {"sent": False, "reason": "approval still pending"}
    # not pending → was decided; confirm it was approved (not rejected)
    from app.db.models import CognitiveApproval, session_scope
    with session_scope() as s:
        row = s.get(CognitiveApproval, approval_id)
        if row is None or row.status != "approved":
            return {"sent": False, "reason": "approval not approved"}
    try:
        res = get_client().send_message(conversation_id, body)
        return {"sent": True, "result": res}
    except TodyError as e:
        return {"sent": False, "error": str(e)}


def request_post(body: str) -> dict:
    """Create-post → pending approval, does NOT post."""
    appr = approvals.request_approval("create_post", payload=body[:500])
    return {"queued": True, "approval": appr,
            "note": "Post will publish only after approval."}
