"""TODY agent — the brain's controlled connection to the TODY app.

Read actions (status/conversations/contacts) run freely. Outbound actions
(send a message, create a post) are HIGH-RISK by policy, so they never fire
directly: they create an approval request, and only execute once Rohit approves.
This is the Phase-1D guardrail before any TODY automation.
"""
from __future__ import annotations

import json
import re

from app.brain.attention_system import Signals
from app.brain.cognitive_loop import process
from app.brain.nurture_engine import childlike_curiosity_message, daily_growth_report
from app.config import get_settings
from app.integrations.tody_client import TodyError, get_client
from app.memory import dialogue_memory, relationship_memory
from app.safety import approvals
from app.safety.audit_logger import log_event


def _canonical_payload(data: dict) -> str:
    """Stable payload string used for approval binding."""
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _send_payload(conversation_id: int, body: str) -> str:
    return _canonical_payload({"conversation_id": conversation_id, "body": body})


def _post_payload(body: str) -> str:
    return _canonical_payload({"body": body})


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


def messages(conversation_id: int, limit: int = 30) -> dict:
    """Recent messages for a conversation (read-only)."""
    return get_client().messages(conversation_id, limit=limit)


def request_send(conversation_id: int, body: str) -> dict:
    """Outbound message → creates a pending approval, does NOT send."""
    payload = _send_payload(conversation_id, body)
    appr = approvals.request_approval("send_message", payload=payload)
    return {"queued": True, "approval": appr,
            "note": "Message will send only after this approval is approved."}


def _recent_reply_openings(conversation_id: int, limit: int = 3) -> list[str]:
    """First ~60 chars of the brain's last few outbound replies — used to stop
    the model from opening every message the same way."""
    turns = dialogue_memory.recall_dialogue(conversation_id, limit=12)
    openings: list[str] = []
    for turn in turns:  # newest first
        title = turn.get("title", "")
        if ":draft_outbound" in title or title.endswith("draft_outbound"):
            opening = (turn.get("content") or "").strip()[:60]
            if opening and opening not in openings:
                openings.append(opening)
        if len(openings) >= limit:
            break
    return openings


def _dedupe_opening(reply: str, recent_openings: list[str]) -> str:
    """If the draft still opens like a recent reply, drop its first sentence —
    a deterministic cure for 'Hi Rohit, it's good to see you' on every message."""
    head = reply.strip()[:25].casefold()
    if not head or not any(o.casefold().startswith(head) for o in recent_openings):
        return reply
    parts = re.split(r"(?<=[.!?])\s+", reply.strip(), maxsplit=1)
    if len(parts) == 2 and len(parts[1]) > 20:
        rest = parts[1]
        return rest[:1].upper() + rest[1:]
    return reply


def draft_reply_to_message(
    conversation_id: int,
    message: str,
    *,
    sender: dict | None = None,
    message_id: int | str | None = None,
    auto_send_guardian: bool | None = None,
) -> dict:
    """Process an inbound TODY message and queue the drafted reply for approval."""
    if dialogue_memory.was_processed("tody", conversation_id, message_id):
        return {
            "processed": False,
            "duplicate": True,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "reason": "message already processed",
        }
    is_guardian = relationship_memory.is_guardian_sender(sender)
    person = relationship_memory.guardian_profile()["name"] if is_guardian else None
    if is_guardian:
        relationship_memory.ensure_guardian_relationship()
    context = dialogue_memory.identity_context(conversation_id, person=person)
    recent_openings = _recent_reply_openings(conversation_id)
    if recent_openings:
        context += (
            "\nYour own recent reply openings — do NOT start like any of these "
            "again, vary completely: "
            + " | ".join(f'"{o}"' for o in recent_openings)
        )
    brain = process(
        message,
        Signals(
            client_impact=3,
            guardian_interest=10 if is_guardian else 6,
            emotional_weight=5 if is_guardian else 3,
        ),
        context=context,
    )
    reply = brain["reply"]
    if reply.lstrip().startswith("[reply fallback"):
        # LLM/provider error: never send internal error traces to TODY.
        # Leave the message unprocessed so the worker retries next tick.
        log_event(
            "tody_reply_llm_error",
            detail=f"conversation_id={conversation_id}; message_id={message_id}",
            risk_tier="low",
        )
        return {
            "processed": False,
            "llm_error": True,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "reason": "LLM provider error; reply suppressed, will retry",
        }
    reply = _dedupe_opening(reply, recent_openings)
    dialogue_memory.remember_turn(
        channel="tody",
        conversation_id=conversation_id,
        direction="inbound",
        body=message,
        person=person,
        importance=10 if is_guardian else 6,
        message_id=str(message_id) if message_id is not None else None,
    )
    dialogue_memory.remember_turn(
        channel="tody",
        conversation_id=conversation_id,
        direction="draft_outbound",
        body=reply,
        person=person,
        importance=10 if is_guardian else 6,
    )
    queued = request_send(conversation_id, reply)
    dialogue_memory.mark_processed("tody", conversation_id, message_id)
    log_event(
        "tody_reply_drafted",
        detail=(
            f"conversation_id={conversation_id}; "
            f"approval_id={queued['approval']['id']}; guardian={is_guardian}"
        ),
        risk_tier="high",
    )
    result = {
        "processed": True,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "guardian_verified": is_guardian,
        "session": dialogue_memory.summarize_conversation(conversation_id),
        "draft": reply,
        "brain": brain,
        "queued": queued,
        "sent": False,
        "note": (
            "Draft queued for approval; nothing was sent to TODY."
            if not is_guardian
            else "Verified guardian message processed. Draft queued; direct send is available through guardian endpoint."
        ),
    }
    if auto_send_guardian is None:
        auto_send_guardian = get_settings().tody_supervised_auto_reply
    if is_guardian and auto_send_guardian:
        approvals.respond(queued["approval"]["id"], approved=True)
        sent = execute_send(queued["approval"]["id"], conversation_id, reply)
        result["direct_send_attempted"] = True
        result["sent"] = sent.get("sent", False)
        result["send_result"] = sent
    return result


def process_latest_message(conversation_id: int, limit: int = 10) -> dict:
    """Read latest TODY message and queue an approval-gated reply draft."""
    data = messages(conversation_id, limit=limit)
    items = _message_items(data)
    if not items:
        return {"processed": False, "reason": "no messages found"}
    latest = items[-1]
    body = _message_body(latest)
    if not body:
        return {"processed": False, "reason": "latest message has no text body"}
    message_id = latest.get("id") or latest.get("message_id")
    if dialogue_memory.was_processed("tody", conversation_id, message_id):
        return {
            "processed": False,
            "duplicate": True,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "reason": "message already processed",
        }
    result = draft_reply_to_message(
        conversation_id,
        body,
        sender=_message_sender(latest),
        message_id=message_id,
    )
    result["source_message"] = {
        "id": message_id,
        "body": body,
    }
    return result


def reply_status(limit: int = 50) -> dict:
    rows = approvals.list_by_action("send_message", status="pending", limit=limit)
    return {"count": len(rows), "pending": rows}


def conversation_status(conversation_id: int) -> dict:
    return {
        "conversation_id": conversation_id,
        "session": dialogue_memory.summarize_conversation(conversation_id),
        "dialogue": dialogue_memory.recall_dialogue(conversation_id, limit=20),
        "auto_reply_enabled": get_settings().tody_supervised_auto_reply,
    }


def direct_reply_to_guardian(conversation_id: int, message: str,
                             sender: dict | None = None,
                             message_id: int | str | None = None) -> dict:
    """Verified-guardian direct reply path.

    This still verifies identity and records the same dialogue/audit trail. It is
    intended only for Rohit Kumar's trusted TODY account.
    """
    profile = relationship_memory.guardian_profile()
    if not profile["direct_reply_allowed"]:
        return {"sent": False, "reason": "guardian direct reply disabled"}
    if not relationship_memory.is_guardian_sender(sender):
        return {"sent": False, "reason": "sender is not verified guardian"}

    return draft_reply_to_message(
        conversation_id,
        message,
        sender=sender,
        message_id=message_id,
        auto_send_guardian=True,
    )


def execute_send(approval_id: int, conversation_id: int, body: str) -> dict:
    """Send a message ONLY if the referenced approval is approved."""
    row = approvals.get_approval(approval_id)
    if row is None:
        return {"sent": False, "reason": "approval not found"}
    if row["status"] == "pending":
        return {"sent": False, "reason": "approval still pending"}
    if row["status"] != "approved" or row["action"] != "send_message":
        return {"sent": False, "reason": "approval not approved"}
    expected_payload = _send_payload(conversation_id, body)
    if row["payload"] != expected_payload:
        log_event(
            "approval_payload_mismatch",
            detail=f"id={approval_id}; action=send_message",
            risk_tier="high",
        )
        return {"sent": False, "reason": "approval payload mismatch"}
    try:
        res = get_client().send_message(conversation_id, body)
        sent_id = _sent_message_id(res)
        dialogue_memory.mark_processed("tody", conversation_id, sent_id)
        log_event(
            "tody_send_executed",
            detail=(
                f"approval_id={approval_id}; conversation_id={conversation_id}; "
                f"sent_message_id={sent_id}"
            ),
            risk_tier="high",
        )
        return {"sent": True, "result": res}
    except TodyError as e:
        log_event(
            "tody_send_failed",
            detail=f"approval_id={approval_id}; error={str(e)}",
            risk_tier="high",
        )
        return {"sent": False, "error": str(e)}


def request_post(body: str) -> dict:
    """Create-post → pending approval, does NOT post."""
    appr = approvals.request_approval("create_post", payload=_post_payload(body))
    return {"queued": True, "approval": appr,
            "note": "Post will publish only after approval."}


def send_daily_growth_report(conversation_id: int) -> dict:
    """Generate and send the daily growth report to verified guardian channel."""
    report = daily_growth_report()
    profile = relationship_memory.guardian_profile()
    sender = {
        "username": profile["tody_username"],
        "email": profile["email"],
        "name": profile["name"],
    }
    return direct_reply_to_guardian(
        conversation_id,
        report["report"],
        sender=sender,
        message_id=f"daily-growth-report-{report['memory_id']}",
    )


def send_childlike_curiosity_message(conversation_id: int) -> dict:
    """Send a proactive child-like curiosity note to verified guardian channel."""
    curiosity = childlike_curiosity_message()
    profile = relationship_memory.guardian_profile()
    sender = {
        "username": profile["tody_username"],
        "email": profile["email"],
        "name": profile["name"],
    }
    return direct_reply_to_guardian(
        conversation_id,
        curiosity["note"],
        sender=sender,
        message_id=f"daily-curiosity-{curiosity['memory_id']}",
    )


def _message_items(data: dict) -> list[dict]:
    if isinstance(data.get("messages"), list):
        return data["messages"]
    if isinstance(data.get("items"), list):
        return data["items"]
    if isinstance(data.get("data"), list):
        return data["data"]
    if isinstance(data, list):
        return data
    return []


def _message_body(row: dict) -> str:
    for key in ("body", "message", "text", "content"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _message_sender(row: dict) -> dict:
    for key in ("sender", "user", "from", "author"):
        value = row.get(key)
        if isinstance(value, dict):
            return value
    return {
        "username": row.get("username") or row.get("sender_username"),
        "email": row.get("email") or row.get("sender_email"),
        "name": row.get("name") or row.get("display_name") or row.get("sender_name"),
    }


def _sent_message_id(data: dict) -> int | str | None:
    if not isinstance(data, dict):
        return None
    msg = data.get("message")
    if isinstance(msg, dict):
        return msg.get("id") or msg.get("message_id")
    return data.get("id") or data.get("message_id")
