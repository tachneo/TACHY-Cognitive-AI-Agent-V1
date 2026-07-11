"""Prospective memory — Shree's scheduler (the "acting in the future" layer).

A human keeps a commitment because it survives in memory between now and when
it is due. Shree's own self-diagnosis named exactly this gap: she could TALK
about the future ("I'll remind you at 3") but not ACT in it, because nothing
persisted the commitment to a due time. This module closes that loop:

  extract(message, conv_id) → the light pool model (gemma, ~0.5s, free on the
                               multi-LLM pool) reads every inbound guardian
                               message and asks "does this ask me to do/say
                               something at a time?" If yes, a row is written
                               with due_at resolved from IST → UTC.
  fire_due()                 → the worker tick (every few seconds) checks for
                               due rows and sends the reminder through the
                               EXISTING approval-gated send path — for the
                               guardian conversation with supervised auto-reply
                               that means auto-approve + execute, exactly like a
                               normal guardian reply; otherwise it stays a
                               pending approval Rohit must clear.

Honesty rule (enforced structurally, not by convention): the reply prompt is
told "row #N created" ONLY when extract() actually wrote a row. Shree may say
"reminder set" only then — she must never claim a future action without a
persisted commitment behind it. The injection lives in tody_agent, fed by the
row id this module returns.

Kill switch: PROSPECTIVE_MEMORY_ENABLED. Only guardian messages can create
reminders (a stranger must not be able to inject scheduled sends).
"""
from __future__ import annotations

import datetime as dt
import json
import re

from app.config import get_settings
from app.db.models import CognitiveScheduledAction, session_scope
from app.safety.audit_logger import log_event

_IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")

# A future-tense commitment, in English or Hinglish. Coarse on purpose: the
# light model does the real classification; this only gates whether we even
# spend a model call (so "hello" doesn't burn tokens).
_FUTURE_CUES = (
    "remind", "reminder", "in ", "at ", "tomorrow", "kal", "parson", "shaam",
    "subah", "dopahar", "raat", "baje", "pm", "am", "tonight", "morning",
    "evening", "after ", "later", "baad mein", "thodi der", "ghante", "minute",
    "hours", "schedule", "set a", "wake me", "ping me", "let me know at",
)

_SYSTEM = (
    "You are Shree's prospective-memory extractor. You read ONE inbound chat "
    "message and decide: does it ask Shree to remind or do something at a "
    "SPECIFIC future time? Resolve relative times (tomorrow, in 2 hours, kal "
    "subah, shaam 5 baje) against the current IST time given below. "
    "If yes, reply with ONLY a JSON object: "
    '{"due_at": "YYYY-MM-DD HH:MM", "text": "the reminder text Shree should '
    'send when due", "confidence": 0.0-1.0}. due_at is 24h IST. If there is no '
    'time-bound commitment, reply with ONLY: {"due_at": null}. No prose.'
)

_MAX_DUE_AHEAD_DAYS = 60


def _now_ist() -> dt.datetime:
    return dt.datetime.now(_IST)


def _utcnow_naive() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _light_complete(prompt: str) -> str:
    """Call the light pool model. Wrapped so tests can monkeypatch it without
    touching the provider stack. max_tokens raised to 512 because gemma with
    enable_thinking spends tokens on reasoning first — at 200 the JSON answer
    was starved and came back EMPTY, so every reminder silently failed."""
    from app.llm.provider import get_light_provider
    return (get_light_provider().complete(_SYSTEM, prompt, max_tokens=512)
            or "").strip()


# ── Deterministic time parser (PRIMARY path) ─────────────────────────
# A reminder is a bounded, structured task ("10:10 am", "shaam 5 baje", "10
# minute baad", "kal subah"). It must NOT depend on a flaky 26B model that
# returns empty — an assistant that can't reliably set an alarm isn't credible.
# This parser handles the common shapes deterministically; the light model is
# only a fallback for genuinely fuzzy phrasing.

_HINGLISH_PARTS = {  # part-of-day → default hour (IST, 24h)
    "subah": 8, "morning": 8, "savere": 8, "tadke": 6,
    "dopahar": 13, "din": 13, "noon": 12, "afternoon": 15,
    "shaam": 17, "sham": 17, "evening": 18,
    "raat": 21, "night": 21, "tonight": 21,
}

# "at 10:10 am", "10:10am", "5 pm", "17:30", "10:35 baje", "5 baje"
_RX_CLOCK = re.compile(
    r"(?:^|\D)(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?|am|pm|baje|bje)?",
    re.I)
# "in 10 minutes", "10 min baad", "2 ghante baad", "after 30 minutes"
_RX_REL = re.compile(
    r"(?:in|after|baad(?:\s+mein)?|thodi\s+der|within)?\s*(\d{1,3})\s*"
    r"(min(?:ute)?s?|m|ghant[ae]|hour?s?|hr?s?|h)\b", re.I)
_RX_REL_SOFT = re.compile(r"thodi\s+der\s+(?:mein|baad)|kuch\s+der", re.I)


def _mk_due(hh: int, mm: int, now_ist: dt.datetime,
            day_offset: int = 0) -> dt.datetime | None:
    """Build a UTC-naive due time from an IST wall clock; if it's already past
    today (and no explicit day given), roll to tomorrow."""
    if not (0 <= hh < 24 and 0 <= mm < 60):
        return None
    due = now_ist.replace(hour=hh, minute=mm, second=0, microsecond=0)
    due += dt.timedelta(days=day_offset)
    if due <= now_ist and day_offset == 0:
        due += dt.timedelta(days=1)
    return due.astimezone(dt.UTC).replace(tzinfo=None)


def _deterministic_parse(message: str,
                         now_ist: dt.datetime | None = None) -> dt.datetime | None:
    """Return the due time (UTC-naive) from a reminder message, or None. Tries
    relative offsets first (unambiguous), then absolute clock + part-of-day."""
    now_ist = now_ist or _now_ist()
    low = (message or "").lower()

    # 1. Relative: "10 minute baad", "in 2 hours", "30 min"
    m = _RX_REL.search(low)
    if m:
        qty = int(m.group(1))
        unit = m.group(2)
        minutes = qty * 60 if unit.startswith(("gh", "hour", "hr", "h")) else qty
        if 1 <= minutes <= _MAX_DUE_AHEAD_DAYS * 24 * 60:
            return (now_ist + dt.timedelta(minutes=minutes)).astimezone(
                dt.UTC).replace(tzinfo=None)
    if _RX_REL_SOFT.search(low):  # "thodi der baad" → ~15 min
        return (now_ist + dt.timedelta(minutes=15)).astimezone(
            dt.UTC).replace(tzinfo=None)

    # Day offset from "kal"/"tomorrow"/"parson"/"aaj"/"today"
    day_offset = 0
    if "parson" in low:
        day_offset = 2
    elif "kal" in low or "tomorrow" in low:
        day_offset = 1

    # 2. Absolute clock: "10:10 am", "5 pm", "17:30", "10:35", "5 baje"
    m = _RX_CLOCK.search(low)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        mer = (m.group(3) or "").replace(".", "").lower()
        if mer == "pm" and hh < 12:
            hh += 12
        elif mer == "am" and hh == 12:
            hh = 0
        elif mer in ("baje", "bje") and hh <= 12:
            # bare "5 baje": use the part-of-day if present, else assume the
            # next occurrence (daytime bias handled by _mk_due roll-forward).
            for part, ph in _HINGLISH_PARTS.items():
                if part in low:
                    if ph >= 12 and hh < 12:
                        hh += 12
                    break
        due = _mk_due(hh, mm, now_ist, day_offset)
        if due is not None:
            return due

    # 3. Part-of-day only ("kal subah", "shaam ko yaad dilana"): the WEAKEST
    # signal — a bare "morning"/"shaam" is usually a greeting, not a reminder
    # ("good morning shree" must NOT create an 8 AM alarm). Require an explicit
    # reminder intent word before trusting a part-of-day alone.
    if _REMINDER_INTENT.search(low):
        for part, ph in _HINGLISH_PARTS.items():
            if part in low:
                return _mk_due(ph, 0, now_ist, day_offset)
    return None


# Explicit "please remind/wake me" intent — gates the weak part-of-day path.
_REMINDER_INTENT = re.compile(
    r"\b(?:remind|reminder|yaad|wake|jaga|alarm|ping\s+me|set\s+a|"
    r"schedule|notify\s+me|batana|bata\s+dena)\b", re.I)


def _extract_json(text: str) -> dict | None:
    """Pull the first {...} block out of a model reply and parse it. The light
    model occasionally wraps JSON in prose or fences; this is tolerant."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def _parse_due_ist(due_str: str) -> dt.datetime | None:
    """"2026-07-09 15:00" (IST) → naive UTC datetime for storage."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            aware = dt.datetime.strptime(due_str.strip(), fmt).replace(tzinfo=_IST)
        except ValueError:
            continue
        return aware.astimezone(dt.UTC).replace(tzinfo=None)
    return None


def _has_future_cue(message: str) -> bool:
    lower = (message or "").lower()
    return any(cue in lower for cue in _FUTURE_CUES)


# Strip the scheduling scaffolding so the fired reminder reads like what the
# task IS, not the raw request. "mujhe 10:35 ko remind kar ki nahane jana hai"
# → "nahane jana hai". Keeps it human when it pings.
_REMINDER_CONNECTOR = re.compile(r"\b(?:ki|that|to)\b\s+", re.I)
# Time/scheduling tokens to scrub from the reminder body.
_TIME_NOISE = re.compile(
    r"\b(?:remind(?:er)?(?:\s+me)?|yaad\s+dila(?:na|o|do)?|mujhe|please|pls|"
    r"at|ko|pe|par|by|around|kar[oi]?|do|dena)\b|"
    r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?|baje|bje)?\b|"
    r"\b(?:kal|parson|aaj|tomorrow|today|subah|shaam|sham|raat|dopahar|"
    r"morning|evening|night|noon|\d+\s*(?:min(?:ute)?s?|ghant[ae]|hours?|hrs?))\b",
    re.I)


def _reminder_text(message: str) -> str:
    msg = (message or "").strip()
    # Prefer the task clause after the last "to/ki/that" connector.
    parts = _REMINDER_CONNECTOR.split(msg)
    tail = parts[-1].strip() if len(parts) > 1 else msg
    # Scrub leftover time/scheduling noise, collapse whitespace.
    cleaned = re.sub(r"\s{2,}", " ", _TIME_NOISE.sub("", tail)).strip(" ,.-")
    body = cleaned if len(cleaned) >= 3 else (tail if len(tail) >= 3 else msg)
    return f"Papa, reminder: {body[:200]}"


def extract(message: str, conversation_id: int | str, *,
            source_message_id: int | str | None = None,
            person: str | None = None,
            is_guardian: bool = True) -> dict:
    """Read one inbound message; if it carries a time-bound commitment, persist
    a scheduled_actions row and return it. Never raises — a reminder-extraction
    failure must not break the reply.

    Only guardian messages create reminders by default (is_guardian=True from
    the caller). A stranger setting Shree's schedule is an injection vector.
    """
    s = get_settings()
    if not s.prospective_memory_enabled or not is_guardian:
        return {"created": False, "reason": "disabled" if not s.prospective_memory_enabled else "non-guardian"}
    msg = (message or "").strip()
    if not msg or len(msg) > 1000 or not _has_future_cue(msg):
        return {"created": False, "reason": "no future cue"}

    now = _utcnow_naive()
    due_utc: dt.datetime | None = None
    text = ""
    actor = "deterministic"

    # PRIMARY: deterministic parser. Reliable, instant, no model call — this is
    # what a reminder deserves. Only if it can't find a time do we ask gemma.
    due_utc = _deterministic_parse(msg)
    if due_utc is not None:
        text = _reminder_text(msg)

    # FALLBACK: fuzzy phrasing the parser missed → the light model.
    if due_utc is None:
        prompt = (
            f"Current IST time: {_now_ist().strftime('%Y-%m-%d %H:%M, %A')}\n"
            f"Inbound message:\n{msg[:600]}\n\n"
            "JSON:"
        )
        try:
            raw = _light_complete(prompt)
        except Exception as exc:  # noqa: BLE001 — never break a reply over extraction
            log_event("prospective_memory_extract_error",
                      detail=f"conv={conversation_id}; {type(exc).__name__}")
            return {"created": False, "reason": "light_model_error"}
        data = _extract_json(raw)
        if not data or data.get("due_at") in (None, "", "null"):
            return {"created": False, "reason": "no_commitment"}
        if float(data.get("confidence") or 0.5) < 0.5:
            return {"created": False, "reason": "low_confidence"}
        due_utc = _parse_due_ist(str(data["due_at"]))
        if due_utc is None:
            return {"created": False, "reason": "bad_due_at"}
        text = str(data.get("text") or msg[:160]).strip()[:600]
        actor = "gemma-intent"

    # Sanity: reject absurd horizons or past times (a reminder for 1999 is junk).
    if due_utc < now - dt.timedelta(minutes=5):
        return {"created": False, "reason": "due_in_past"}
    if due_utc > now + dt.timedelta(days=_MAX_DUE_AHEAD_DAYS):
        return {"created": False, "reason": "due_too_far"}
    text = (text or msg[:160]).strip()[:600]

    try:
        with session_scope() as sess:
            row = CognitiveScheduledAction(
                conversation_id=int(conversation_id),
                text=text,
                due_at=due_utc,
                source_message_id=str(source_message_id) if source_message_id is not None else None,
                source_text=msg[:400],
                person=person,
                status="pending",
                actor=actor,
            )
            sess.add(row)
            sess.flush()
            rid = int(row.id)
    except Exception as exc:  # noqa: BLE001 — a missing table / DB error must
        # NEVER break reply drafting. Reminder extraction is a non-critical
        # enhancement; the reply still goes out, just without a persisted row.
        log_event("prospective_memory_db_error",
                  detail=f"conv={conversation_id}; {type(exc).__name__}: {str(exc)[:120]}")
        return {"created": False, "reason": "db_error"}
    due_ist = due_utc.replace(tzinfo=dt.UTC).astimezone(_IST)
    log_event("prospective_memory_created",
              detail=f"id={rid}; conv={conversation_id}; due_utc={due_utc.isoformat()}; "
                     f"text={text[:80]}")
    return {"created": True, "id": rid, "due_at_utc": due_utc.isoformat(),
            "due_at_ist": due_ist.strftime("%Y-%m-%d %H:%M %Z"), "text": text}


def injection_hint(extract_result: dict) -> str:
    """The context line that tells the reply prompt a real row was created —
    so Shree may honestly say 'reminder set'. Empty when nothing was created."""
    if not extract_result.get("created"):
        return ""
    rid = extract_result["id"]
    due = extract_result.get("due_at_ist", "?")
    text = extract_result.get("text", "")
    return (
        f"\n[PROSPECTIVE MEMORY: reminder row #{rid} was created and will fire "
        f"at {due} IST with the text: \"{text}\". BECAUSE this row exists, you "
        f"may honestly tell the user 'reminder set' or 'I'll ping you at {due}'. "
        f"Do NOT claim a reminder is set for any other time or task — only this "
        f"row exists. Do NOT mention 'row' or 'pipeline' to the user; just "
        f"confirm naturally.]\n"
    )


def list_due(*, now: dt.datetime | None = None, limit: int = 20) -> list[dict]:
    """Pending rows whose due_at has arrived (UTC). For the worker tick."""
    now = now or _utcnow_naive()
    with session_scope() as sess:
        rows = (sess.query(CognitiveScheduledAction)
                .filter(CognitiveScheduledAction.status == "pending",
                        CognitiveScheduledAction.due_at <= now)
                .order_by(CognitiveScheduledAction.due_at.asc())
                .limit(limit).all())
        return [{"id": int(r.id), "conversation_id": int(r.conversation_id),
                 "text": r.text, "due_at": r.due_at.isoformat(),
                 "person": r.person} for r in rows]


def fire_due(*, limit: int = 10) -> dict:
    """Fire all due reminders through the existing approval-gated send path.

    For the guardian conversation with supervised auto-reply ON, this mirrors a
    normal guardian reply: request approval → auto-approve → execute_send. With
    auto-reply OFF (or a non-guardian conversation), the approval is left
    pending for Rohit to clear — Shree never sends autonomously without the same
    gate that governs every other outbound message.
    """
    s = get_settings()
    if not s.prospective_memory_enabled:
        return {"enabled": False, "fired": []}
    from app.agents import tody_agent
    from app.safety import approvals

    due = list_due(limit=limit)
    fired: list[dict] = []
    for item in due:
        rid = item["id"]
        conv_id = item["conversation_id"]
        text = item["text"]
        try:
            queued = tody_agent.request_send(conv_id, text)
            approval_id = int(queued["approval"]["id"])
            sent = False
            # Supervised auto-reply mirrors the normal guardian reply path:
            # auto-approve + execute. Otherwise leave it for Rohit to clear.
            if s.tody_supervised_auto_reply:
                approvals.respond(approval_id, approved=True)
                res = tody_agent.execute_send(approval_id, conv_id, text)
                sent = bool(res.get("sent"))
            status = "fired" if sent else ("pending_approval"
                                           if not s.tody_supervised_auto_reply
                                           else "failed")
            _mark(rid, status=status, approval_id=approval_id)
            log_event("prospective_memory_fired",
                      detail=f"id={rid}; conv={conv_id}; approval={approval_id}; "
                             f"sent={sent}; status={status}",
                      risk_tier="high")
            fired.append({"id": rid, "conversation_id": conv_id,
                          "sent": sent, "status": status,
                          "approval_id": approval_id})
        except Exception as exc:  # noqa: BLE001 — one bad row must not stop the rest
            _mark(rid, status="failed")
            log_event("prospective_memory_fire_error",
                      detail=f"id={rid}; {type(exc).__name__}: {str(exc)[:120]}",
                      risk_tier="medium")
            fired.append({"id": rid, "error": type(exc).__name__})
    return {"enabled": True, "fired_count": len(fired), "fired": fired}


def _mark(row_id: int, *, status: str, approval_id: int | None = None) -> None:
    with session_scope() as sess:
        row = sess.get(CognitiveScheduledAction, int(row_id))
        if row is None:
            return
        row.status = status
        if approval_id is not None:
            row.approval_id = approval_id
        if status in {"fired", "failed"}:
            row.fired_at = _utcnow_naive()


def list_pending(*, limit: int = 20) -> list[dict]:
    with session_scope() as sess:
        rows = (sess.query(CognitiveScheduledAction)
                .filter(CognitiveScheduledAction.status == "pending")
                .order_by(CognitiveScheduledAction.due_at.asc())
                .limit(limit).all())
        return [{"id": int(r.id), "conversation_id": int(r.conversation_id),
                 "text": r.text,
                 "due_at_ist": r.due_at.replace(tzinfo=dt.UTC)
                                 .astimezone(_IST).strftime("%Y-%m-%d %H:%M %Z")
                 if r.due_at else None,
                 "status": r.status} for r in rows]


def cancel(row_id: int) -> bool:
    with session_scope() as sess:
        row = sess.get(CognitiveScheduledAction, int(row_id))
        if row is None or row.status != "pending":
            return False
        row.status = "cancelled"
        log_event("prospective_memory_cancelled", detail=f"id={row_id}")
        return True


def describe() -> dict:
    return {"enabled": get_settings().prospective_memory_enabled,
            "pending": list_pending(limit=10),
            "due_now": len(list_due())}
