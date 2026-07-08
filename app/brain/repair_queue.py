"""Repair queue — evidence-tiered memory of Shree's own failures (metacognitive
loop, step 2 of 4).

The problem it solves: Shree NOTICES failures in many places (Rohit corrects
her, a user complains, a reply truncates, self_review flags a leak, the worker
crashes) — but each noticing evaporated into its own log. Nothing accumulated,
so nothing ever became "I keep failing this way, I should fix the cause."

This module is that accumulator. Every noticing source calls note_failure()
with a SIGNATURE — the structural shape of the mistake ("reply-too-long",
"worker-crash:TypeError"), not the text of one instance. Rows accumulate
recurrence until their evidence tier's threshold marks them repair-READY;
self_diagnose reads ready rows and the self-improvement layer fixes the cause.

Evidence tiers (an LLM judging an LLM is the WEAKEST signal, so self-critique
never triggers a repair on its own):

  1  guardian correction        → ready immediately (Rohit said it's wrong)
  2  conversational ground truth → ready when it recurs, and — for strangers —
     (complaints, repeats)         only across ≥2 distinct people, so one
                                   annoyed (or manipulative) user can't steer
                                   what Shree changes about herself
  3  hard system events          → ready on recurrence (truncation, guard skip,
                                   worker traceback)
  4  LLM self-critique           → NEVER ready alone; corroboration by a
                                   higher tier on the same signature upgrades it

One-fix-per-signature: if a signature recurs AFTER being fixed, it escalates to
Rohit instead of being fixed again — self-repair must never oscillate. The
escalation lands in the audit log where the proactive layer already looks, so
she tells Papa herself.

Never raises into a caller: noticing a failure must never cause one.
Kill switch: REPAIR_QUEUE_ENABLED.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from app.config import get_settings
from app.db.models import CognitiveRepairIntention, session_scope
from app.safety.audit_logger import log_event_safe

# Recurrence needed per tier before a row becomes repair-ready.
_READY_AT = {1: 1, 2: 2, 3: 2}          # tier 4 is intentionally absent
_MAX_PEOPLE_TRACKED = 20
_VALID_FIX = {"memory", "directive", "config", "code", "capability",
              "environment", "unknown"}

# T2 — conversational ground truth: the user telling Shree, in their own words,
# that a PAST reply failed. Coarse cues on purpose; the signature categorises.
_CONVERSATIONAL_CUES = (
    ("reply-too-long", ("itna lamba", "lamba kyo", "too long", "bada message",
                        "chhota likho", "short me likho", "kam likho",
                        "lambe message")),
    ("not-replying", ("jawab kyo nahi", "reply kyo nahi", "jawab nahi de",
                      "reply nahi de", "answer nahi", "kyu nahi bol",
                      "not replying", "no reply", "jawab do")),
    ("wrong-answer", ("galat jawab", "galat bataya", "galat tarike", "ye galat",
                      "wrong answer", "galat reply", "galat hai ye")),
    ("repeated-reply", ("same baat", "wahi baat phir", "phir se wahi", "repeat kar",
                        "already bataya", "bata chuki", "ek hi baat")),
    ("robotic-reply", ("robot jais", "scripted", "machine jais", "bot jais",
                       "rata hua", "insaan jaise baat")),
)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9:+-]+", "-", (text or "").strip().lower())
    return s.strip("-")[:160] or "unknown"


def note_failure(signature: str, *, tier: int, source: str = "",
                 sample: str = "", conversation_id: int | None = None,
                 person: str | None = None, guardian: bool = False,
                 fix_class: str = "unknown") -> dict:
    """Record one occurrence of a failure signature. Upserts the row,
    accumulates recurrence/people, applies the tier thresholds, and handles the
    fixed→escalated transition. NEVER raises."""
    try:
        return _note(signature, tier=tier, source=source, sample=sample,
                     conversation_id=conversation_id, person=person,
                     guardian=guardian, fix_class=fix_class)
    except Exception as exc:  # noqa: BLE001 — noticing must never break a reply
        log_event_safe("repair_queue_error",
                       detail=f"sig={signature[:60]}; {type(exc).__name__}",
                       risk_tier="low", actor="repair_queue")
        return {"noted": False, "reason": type(exc).__name__}


def _note(signature: str, *, tier: int, source: str, sample: str,
          conversation_id: int | None, person: str | None, guardian: bool,
          fix_class: str) -> dict:
    if not get_settings().repair_queue_enabled:
        return {"noted": False, "reason": "disabled"}
    sig = _slug(signature)
    tier = min(max(int(tier), 1), 4)
    if fix_class not in _VALID_FIX:
        fix_class = "unknown"
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)

    with session_scope() as sess:
        row = (sess.query(CognitiveRepairIntention)
               .filter(CognitiveRepairIntention.signature == sig).first())
        if row is None:
            row = CognitiveRepairIntention(
                signature=sig, evidence_tier=tier, fix_class=fix_class,
                recurrence=1, guardian_involved=bool(guardian),
                people=json.dumps([person] if (person and not guardian) else []),
                sample=(sample or "")[:400], source=(source or "")[:64],
                conversation_id=conversation_id, status="observing",
                last_seen=now)
            sess.add(row)
            sess.flush()
        else:
            row.recurrence = int(row.recurrence or 0) + 1
            row.evidence_tier = min(int(row.evidence_tier or 4), tier)
            row.guardian_involved = bool(row.guardian_involved) or bool(guardian)
            if sample:
                row.sample = sample[:400]
            if source:
                row.source = source[:64]
            if conversation_id is not None:
                row.conversation_id = conversation_id
            if fix_class != "unknown" and row.fix_class == "unknown":
                row.fix_class = fix_class
            if person and not guardian:
                try:
                    people = json.loads(row.people or "[]")
                except ValueError:
                    people = []
                if person not in people and len(people) < _MAX_PEOPLE_TRACKED:
                    people.append(person)
                    row.people = json.dumps(people)
            row.last_seen = now

        # fixed → recurred: escalate to Rohit, never re-fix (anti-oscillation).
        if row.status == "fixed":
            row.status = "escalated"
            log_event_safe(
                "repair_escalated",
                detail=(f"signature={sig}; recurred AFTER a fix "
                        f"(recurrence={row.recurrence}); needs Rohit"),
                risk_tier="high", actor="repair_queue")
        elif row.status == "observing" and _is_ready(row):
            row.status = "ready"
            log_event_safe(
                "repair_ready",
                detail=(f"signature={sig}; tier={row.evidence_tier}; "
                        f"recurrence={row.recurrence}; fix_class={row.fix_class}"),
                risk_tier="medium", actor="repair_queue")
        return {"noted": True, "signature": sig, "status": row.status,
                "recurrence": int(row.recurrence),
                "tier": int(row.evidence_tier)}


def _is_ready(row: CognitiveRepairIntention) -> bool:
    tier = int(row.evidence_tier or 4)
    if tier not in _READY_AT:          # tier 4: hypothesis only, never alone
        return False
    if int(row.recurrence or 0) < _READY_AT[tier]:
        return False
    if tier == 2 and not row.guardian_involved:
        # Strangers can't steer her self-modification alone: require the same
        # complaint from ≥2 distinct people before it becomes repair-worthy.
        try:
            people = json.loads(row.people or "[]")
        except ValueError:
            people = []
        return len(people) >= 2
    return True


def note_conversational_signals(message: str, *, person: str | None = None,
                                conversation_id: int | None = None,
                                guardian: bool = False) -> list[str]:
    """T2 detector: is THIS inbound message the user complaining about a past
    reply? Called from the reply path before drafting — ground truth straight
    from the person, no model opinion involved. Returns noted signatures."""
    lower = (message or "").lower()
    if not lower or len(lower) > 500:
        return []
    noted: list[str] = []
    for sig, cues in _CONVERSATIONAL_CUES:
        if any(cue in lower for cue in cues):
            note_failure(sig, tier=2, source="conversation",
                         sample=message[:200], conversation_id=conversation_id,
                         person=person, guardian=guardian,
                         fix_class="directive")
            noted.append(sig)
    return noted


def ready(limit: int = 10) -> list[dict]:
    """Repair-ready rows, strongest evidence first — read by self_diagnose."""
    try:
        with session_scope() as sess:
            rows = (sess.query(CognitiveRepairIntention)
                    .filter(CognitiveRepairIntention.status == "ready")
                    .order_by(CognitiveRepairIntention.evidence_tier.asc(),
                              CognitiveRepairIntention.recurrence.desc())
                    .limit(limit).all())
            return [_as_dict(r) for r in rows]
    except Exception:  # noqa: BLE001
        return []


def mark(signature: str, *, status: str, note: str = "") -> bool:
    """Move a signature to repairing/fixed/dismissed (the repair layer calls
    this as it works). fixed stamps repaired_at — the anti-oscillation anchor."""
    if status not in {"observing", "ready", "repairing", "fixed",
                      "escalated", "dismissed"}:
        return False
    try:
        with session_scope() as sess:
            row = (sess.query(CognitiveRepairIntention)
                   .filter(CognitiveRepairIntention.signature == _slug(signature))
                   .first())
            if row is None:
                return False
            row.status = status
            if note:
                row.repair_note = note[:400]
            if status == "fixed":
                row.repaired_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
            return True
    except Exception:  # noqa: BLE001
        return False


def describe(limit: int = 15) -> dict:
    """Observability: the queue as Shree (and Rohit) can see it."""
    try:
        with session_scope() as sess:
            rows = (sess.query(CognitiveRepairIntention)
                    .order_by(CognitiveRepairIntention.last_seen.desc())
                    .limit(limit).all())
            counts: dict[str, int] = {}
            for r in sess.query(CognitiveRepairIntention).all():
                counts[r.status] = counts.get(r.status, 0) + 1
            return {"enabled": get_settings().repair_queue_enabled,
                    "counts": counts, "recent": [_as_dict(r) for r in rows]}
    except Exception:  # noqa: BLE001
        return {"enabled": get_settings().repair_queue_enabled,
                "counts": {}, "recent": []}


def _as_dict(r: CognitiveRepairIntention) -> dict:
    return {"signature": r.signature, "tier": int(r.evidence_tier or 4),
            "fix_class": r.fix_class, "recurrence": int(r.recurrence or 0),
            "guardian": bool(r.guardian_involved), "status": r.status,
            "sample": (r.sample or "")[:160], "source": r.source,
            "conversation_id": r.conversation_id,
            "last_seen": r.last_seen.isoformat() if r.last_seen else None}
