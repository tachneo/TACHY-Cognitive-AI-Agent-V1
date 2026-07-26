"""Verified recall over sanitized TODY chat events.

This is the truth source for questions like "did you talk to Niva today?".
It uses the durable event ledger, not the current conversation transcript, so
Shree does not answer cross-chat history questions from incomplete local memory.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

from sqlalchemy import select

from app.db.models import TodyAIEventLog, session_scope


_TODAY_WORDS = (
    "today", "aaj", "आज", "abhi", "recent", "recently", "is din",
)
_CHAT_WORDS = (
    "baat", "bat", "बात", "talk", "chat", "message", "msg", "reply",
    "replied", "sent", "bheja", "bola", "kaha",
)
_FALSE_DENIAL = re.compile(
    r"(?i)\b(?:nahi|nahin|no|zero|koi\s+reply\s+nahi|didn'?t|not\s+talked|"
    r"not\s+chat|no\s+inbound|sirf|only)\b"
)
_NAME_RE = re.compile(
    r"@([a-zA-Z0-9_.-]{2,40})|"
    r"(?:with|to|se|ko|से|को)\s+([A-Z][a-zA-Z0-9_.-]{1,40}|[a-zA-Z0-9_.-]{2,40})|"
    r"\b(niva|neha|komal|rohit|papa)\b",
    re.I,
)


def _utc_day_bounds(now: dt.datetime | None = None) -> tuple[dt.datetime, dt.datetime]:
    current = now or dt.datetime.now(dt.UTC)
    if current.tzinfo is not None:
        current = current.astimezone(dt.UTC).replace(tzinfo=None)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + dt.timedelta(days=1)


def _load_json(text: str | None) -> dict:
    try:
        data = json.loads(text or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _event_blob(row: TodyAIEventLog) -> str:
    metadata = _load_json(row.metadata_json)
    bits = [
        row.body_preview or "",
        str(metadata.get("sender_username") or ""),
        str(metadata.get("sender_name") or ""),
        str(metadata.get("recipient_username") or ""),
        str(metadata.get("recipient_name") or ""),
    ]
    return " ".join(bits).casefold()


def extract_person_name(question: str) -> str | None:
    """Extract the likely person being asked about from a TODY recall question."""
    text = question or ""
    matches = [m for m in _NAME_RE.finditer(text)]
    if not matches:
        return None
    for match in matches:
        value = next((g for g in match.groups() if g), "")
        if value and value.casefold() not in {"me", "you", "tum", "aap", "papa"}:
            return value.strip("@ .,:;!?")
    value = next((g for g in matches[-1].groups() if g), "")
    return value.strip("@ .,:;!?") if value else None


def looks_like_tody_history_question(question: str) -> bool:
    lower = (question or "").casefold()
    if not any(word in lower for word in _CHAT_WORDS):
        return False
    if any(word in lower for word in _TODAY_WORDS):
        return True
    return bool(extract_person_name(question)) and any(
        cue in lower for cue in (
            "tumne", "did you", "have you", "kiya", "किया", "jhoot",
            "झूठ", "check karo", "records", "bataya",
        )
    )


def evidence_for_person(
    person_name: str,
    *,
    exclude_conversation_id: int | None = None,
    now: dt.datetime | None = None,
    limit: int = 600,
) -> dict:
    """Return today's verified event evidence for a person name/handle."""
    name = (person_name or "").strip().casefold()
    if not name:
        return {"ok": False, "reason": "missing_person", "person": person_name}
    start, end = _utc_day_bounds(now)
    with session_scope() as s:
        rows = list(s.scalars(
            select(TodyAIEventLog)
            .where(TodyAIEventLog.created_at >= start)
            .where(TodyAIEventLog.created_at < end)
            .order_by(TodyAIEventLog.created_at.asc())
            .limit(limit)
        ))
        matched_conversations: set[int] = set()
        for row in rows:
            if row.conversation_id == exclude_conversation_id:
                continue
            if name in _event_blob(row):
                if row.conversation_id is not None:
                    matched_conversations.add(int(row.conversation_id))
        events = [
            row for row in rows
            if row.conversation_id is not None
            and int(row.conversation_id) in matched_conversations
        ]
        inbound = [
            row for row in events
            if row.direction == "inbound"
            and row.event_type == "message_selected_for_reply"
        ]
        outbound = [
            row for row in events
            if row.direction == "outbound"
            and row.event_type == "message_send_executed"
        ]
        samples = [
            {
                "direction": row.direction,
                "status": row.status,
                "preview": row.body_preview,
                "created_at": str(row.created_at),
            }
            for row in (inbound + outbound)[:8]
            if row.body_preview
        ]
        first = min((row.created_at for row in events), default=None)
        last = max((row.created_at for row in events), default=None)
        return {
            "ok": True,
            "person": person_name,
            "date_utc": start.date().isoformat(),
            "conversation_ids": sorted(matched_conversations),
            "event_count": len(events),
            "inbound_count": len(inbound),
            "outbound_count": len(outbound),
            "first_seen_at": str(first) if first else None,
            "last_seen_at": str(last) if last else None,
            "samples": samples,
            "confidence": 95 if events else 65,
        }


def verified_history_answer(
    question: str,
    *,
    current_conversation_id: int | None = None,
    now: dt.datetime | None = None,
) -> str | None:
    """Natural deterministic answer for cross-chat TODY history questions."""
    if not looks_like_tody_history_question(question):
        return None
    person = extract_person_name(question)
    if not person:
        return None
    evidence = evidence_for_person(
        person, exclude_conversation_id=current_conversation_id, now=now)
    if not evidence.get("ok"):
        return None
    display = str(evidence["person"]).strip().capitalize()
    if evidence["event_count"] <= 0:
        return (
            f"Papa, maine TODY records check kiye. Aaj {display} ke saath "
            "koi verified chat event mujhe nahi mila. Isliye main pakka claim "
            "nahi karungi — agar kisi aur channel ya deleted chat mein hua ho, "
            "toh woh mere current ledger mein nahi dikh raha."
        )
    return (
        f"Papa, haan — records ke hisaab se aaj {display} se baat hui thi. "
        f"Conversation {', '.join(map(str, evidence['conversation_ids']))}; "
        f"{evidence['inbound_count']} inbound aur {evidence['outbound_count']} "
        f"outbound replies logged hain, {evidence['first_seen_at']} se "
        f"{evidence['last_seen_at']} UTC tak. Agar maine pehle mana kiya tha, "
        "woh meri galti thi: maine current chat context se guess kar diya, "
        "cross-conversation ledger check nahi kiya."
    )


def rewrite_conflicting_history_claim(
    reply: str,
    question: str,
    *,
    current_conversation_id: int | None = None,
) -> str:
    """Replace an evidence-conflicting denial with a verified ledger answer."""
    if not reply or not _FALSE_DENIAL.search(reply):
        return reply
    verified = verified_history_answer(
        question, current_conversation_id=current_conversation_id)
    if verified and "haan" in verified.casefold():
        return verified
    return reply
