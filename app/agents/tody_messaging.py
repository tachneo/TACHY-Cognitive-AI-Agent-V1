"""Directed messaging (Phase 2A) — Shree messages other TODY users for Papa.

Rohit can instruct Shree ("send message to @arjun: call me", "tell rohitsingh
the meeting is at 5") and she resolves the username → starts/opens a direct
conversation → sends. All outbound directed sends are HIGH-risk and go through
the approval workflow (proposed by the action engine), so a message is only
sent after the guardian approves it (or auto-approve for the guardian channel).
"""
from __future__ import annotations

import re

from app.integrations.tody_client import TodyError, get_client
from app.safety.audit_logger import log_event


def resolve_username(username: str) -> dict | None:
    """Look up a TODY user by @username → {uuid, username, display_name}."""
    handle = (username or "").lstrip("@").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.]{2,40}", handle):
        return None
    try:
        data = get_client()._post("/v1/contacts/search_username.php",
                                  {"username": handle})
    except TodyError:
        return None
    user = (data or {}).get("user")
    if not user or not user.get("uuid"):
        return None
    return {"uuid": user["uuid"], "username": user.get("username", handle),
            "display_name": user.get("display_name", handle)}


def send_direct(username: str, body: str) -> dict:
    """Resolve the user, open a direct conversation, and send. Returns a
    result dict; called only by the approved action-engine path."""
    user = resolve_username(username)
    if user is None:
        return {"sent": False, "reason": f"user @{username} not found"}
    text = (body or "").strip()
    if not text:
        return {"sent": False, "reason": "empty message"}
    try:
        conv = get_client().start_direct(user["uuid"])
        conversation_id = conv.get("conversation_id")
        if not conversation_id:
            return {"sent": False, "reason": "could not open conversation"}
        res = get_client().send_message(int(conversation_id), text)
    except TodyError as exc:
        return {"sent": False, "reason": f"tody error: {exc}"}
    log_event("directed_message_sent",
              detail=f"to=@{user['username']}; conversation_id={conversation_id}",
              risk_tier="high")
    return {"sent": True, "to": user["username"],
            "display_name": user["display_name"],
            "conversation_id": conversation_id, "result": res}


# ── Command parsing (guardian instructions) ─────────────────────

# "send message to @arjun: call me tonight"
# "message @arjun that the meeting moved to 5"
# "tell rohitsingh i will be late"
# "inform @arjun about the demo tomorrow"
_CMD = re.compile(
    r"^\s*(?:can you\s+|please\s+)?"
    r"(?:send (?:a )?message to|message|msg|text|tell|inform|ping|"
    r"reach out to|chat with|write to)\s+"
    r"@?([A-Za-z0-9_.]{2,40})\s*"
    r"(?::|,|-|\bthat\b|\babout\b|\bsaying\b|\bto say\b)?\s*"
    r"(.*)$",
    re.I | re.S,
)


def parse_command(message: str) -> dict | None:
    """Parse a directed-message instruction into {username, body}, or None."""
    m = _CMD.match((message or "").strip())
    if not m:
        return None
    username, body = m.group(1), (m.group(2) or "").strip(" :,-\n")
    # Guard against matching generic verbs like "message me" / "tell me".
    if username.lower() in {"me", "you", "him", "her", "them", "us", "papa"}:
        return None
    if not body:
        return None
    return {"username": username, "body": body}
