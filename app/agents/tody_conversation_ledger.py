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

from app.brain import language_grammar
from app.db.models import TodyAIEventLog, session_scope


_TODAY_WORDS = (
    "today", "aaj", "आज", "abhi", "recent", "recently", "is din",
)
_EVER_WORDS = (
    "kabhi", "कभी", "ever", "anytime", "any time", "ab tak", "pehle",
)
_YESTERDAY_WORDS = ("kal", "कल", "yesterday")
_DAY_BEFORE_WORDS = ("parso", "परसों", "day before yesterday")
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
    r"\b(?:with|to|se|ko|से|को)\b\s+([A-Z][a-zA-Z0-9_.-]{1,40}|[a-zA-Z0-9_.-]{2,40})|"
    r"\b(niva|neha|komal|rohit|papa)\b",
    re.I,
)
_NAME_STOP = {"me", "you", "tum", "aap", "papa", "baat", "chat", "message", "msg"}


def _utc_day_bounds(now: dt.datetime | None = None) -> tuple[dt.datetime, dt.datetime]:
    current = now or dt.datetime.now(dt.UTC)
    if current.tzinfo is not None:
        current = current.astimezone(dt.UTC).replace(tzinfo=None)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + dt.timedelta(days=1)


_IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _utc_naive(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(dt.UTC).replace(tzinfo=None)


def _local_day_bounds_utc(offset_days: int, now: dt.datetime | None = None) -> tuple[dt.datetime, dt.datetime]:
    current = now or dt.datetime.now(dt.UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.UTC)
    local = current.astimezone(_IST) + dt.timedelta(days=offset_days)
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + dt.timedelta(days=1)
    return _utc_naive(start_local.astimezone(dt.UTC)), _utc_naive(end_local.astimezone(dt.UTC))


def _scope_from_question(question: str) -> str:
    lower = (question or "").casefold()
    # "aaj nahi, kabhi..." must be all-time, not today.
    if any(word in lower for word in _EVER_WORDS):
        return "all_time"
    if "kal ya parso" in lower or "kal or parso" in lower or "yesterday or day before" in lower:
        return "past_2_days"
    if any(word in lower for word in _DAY_BEFORE_WORDS):
        return "day_before_yesterday"
    if any(word in lower for word in _YESTERDAY_WORDS):
        return "yesterday"
    if any(word in lower for word in _TODAY_WORDS):
        return "today"
    return "all_time"


def _scope_bounds(scope: str, now: dt.datetime | None = None) -> tuple[dt.datetime, dt.datetime] | None:
    if scope == "all_time":
        return None
    if scope == "yesterday":
        return _local_day_bounds_utc(-1, now)
    if scope == "day_before_yesterday":
        return _local_day_bounds_utc(-2, now)
    if scope == "past_2_days":
        start, _ = _local_day_bounds_utc(-2, now)
        _, end = _local_day_bounds_utc(-1, now)
        return start, end
    return _local_day_bounds_utc(0, now)


def _scope_label(scope: str) -> str:
    return {
        "today": "aaj",
        "yesterday": "kal",
        "day_before_yesterday": "parso",
        "past_2_days": "kal ya parso",
        "all_time": "kabhi bhi",
    }.get(scope, "is scope mein")


def _fmt_ist(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    moment = value.replace(tzinfo=dt.UTC) if value.tzinfo is None else value.astimezone(dt.UTC)
    return moment.astimezone(_IST).strftime("%Y-%m-%d %H:%M IST")


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


def _recent_texts_for_conversation(conversation_id: int | None, *, limit: int = 20) -> list[str]:
    if conversation_id is None:
        return []
    with session_scope() as s:
        rows = list(s.scalars(
            select(TodyAIEventLog.body_preview)
            .where(TodyAIEventLog.conversation_id == conversation_id)
            .order_by(TodyAIEventLog.created_at.desc())
            .limit(limit)
        ))
    return [text or "" for text in reversed(rows)]


def extract_person_name(question: str, *, current_conversation_id: int | None = None) -> str | None:
    """Extract the likely person being asked about from a TODY recall question."""
    text = question or ""
    matches = [m for m in _NAME_RE.finditer(text)]
    if not matches:
        return language_grammar.resolve_recent_person(
            text,
            _recent_texts_for_conversation(current_conversation_id),
        )
    for match in matches:
        value = next((g for g in match.groups() if g), "")
        if value and value.casefold() not in _NAME_STOP:
            return value.strip("@ .,:;!?")
    value = next((g for g in matches[-1].groups() if g), "")
    if value:
        return value.strip("@ .,:;!?")
    return language_grammar.resolve_recent_person(
        text,
        _recent_texts_for_conversation(current_conversation_id),
    )


def looks_like_tody_history_question(
    question: str,
    *,
    current_conversation_id: int | None = None,
) -> bool:
    lower = (question or "").casefold()
    if not any(word in lower for word in _CHAT_WORDS):
        return False
    if any(word in lower for word in (*_TODAY_WORDS, *_EVER_WORDS, *_YESTERDAY_WORDS, *_DAY_BEFORE_WORDS)):
        return True
    return bool(extract_person_name(
        question, current_conversation_id=current_conversation_id,
    )) and any(
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
    scope: str = "today",
    limit: int = 600,
) -> dict:
    """Return verified event evidence for a person name/handle."""
    name = (person_name or "").strip().casefold()
    if not name:
        return {"ok": False, "reason": "missing_person", "person": person_name}
    bounds = _scope_bounds(scope, now)
    with session_scope() as s:
        stmt = select(TodyAIEventLog).order_by(TodyAIEventLog.created_at.asc())
        if bounds is not None:
            start, end = bounds
            stmt = stmt.where(TodyAIEventLog.created_at >= start).where(TodyAIEventLog.created_at < end)
        rows = list(s.scalars(stmt.limit(limit if scope != "all_time" else max(limit, 5000))))
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
            "scope": scope,
            "scope_label": _scope_label(scope),
            "date_utc": bounds[0].date().isoformat() if bounds else None,
            "conversation_ids": sorted(matched_conversations),
            "event_count": len(events),
            "inbound_count": len(inbound),
            "outbound_count": len(outbound),
            "first_seen_at": str(first) if first else None,
            "last_seen_at": str(last) if last else None,
            "first_seen_ist": _fmt_ist(first),
            "last_seen_ist": _fmt_ist(last),
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
    if not looks_like_tody_history_question(
        question, current_conversation_id=current_conversation_id,
    ):
        return None
    person = extract_person_name(
        question, current_conversation_id=current_conversation_id)
    if not person:
        return None
    scope = _scope_from_question(question)
    evidence = evidence_for_person(
        person, exclude_conversation_id=current_conversation_id, now=now,
        scope=scope)
    if not evidence.get("ok"):
        return None
    display = str(evidence["person"]).strip().capitalize()
    scope_label = str(evidence.get("scope_label") or _scope_label(scope))
    if evidence["event_count"] <= 0:
        return (
            f"Papa, maine TODY records check kiye. {scope_label.capitalize()} "
            f"{display} ke saath "
            "koi verified chat event mujhe nahi mila. Isliye main pakka claim "
            "nahi karungi — agar kisi aur channel ya deleted chat mein hua ho, "
            "toh woh mere current ledger mein nahi dikh raha."
        )
    return (
        f"Papa, haan — records ke hisaab se {scope_label} {display} se baat hui thi. "
        f"Conversation {', '.join(map(str, evidence['conversation_ids']))}; "
        f"{evidence['inbound_count']} inbound aur {evidence['outbound_count']} "
        f"outbound replies logged hain, {evidence['first_seen_ist']} se "
        f"{evidence['last_seen_ist']} tak. Agar maine pehle mana kiya tha, "
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
